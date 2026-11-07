import math
import os
import random
import time
from typing import Optional

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
    QLinearGradient, QRadialGradient, QPolygonF
)

from desktop_scanner import DesktopItem
from sound_fx import sound_fx
import win32_helper


class DebrisParticle:
    """Realistic physical desktop dust/lint particle."""
    def __init__(self, x: float, y: float, target_x: float, target_y: float):
        self.x = x
        self.y = y
        self.target_x = target_x
        self.target_y = target_y
        self.life = 1.0
        self.decay = random.uniform(0.04, 0.08)
        self.w = random.uniform(1.2, 2.8)
        self.h = random.uniform(1.0, 2.2)
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(1.0, 3.0)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        v = random.randint(180, 230)
        self.color = QColor(v, v, int(v * 0.95))

    def update(self):
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy) + 0.1
        ax = (dx / dist) * 5.0
        ay = (dy / dist) * 5.0
        self.vx = self.vx * 0.85 + ax * 0.22
        self.vy = self.vy * 0.85 + ay * 0.22
        self.x += self.vx
        self.y += self.vy
        self.life -= self.decay
        return self.life > 0


class OverlayWindow(QWidget):
    # Emits (sucked_items, mode)
    finished_cleaning = pyqtSignal(list, str)

    STATE_DOCK = "dock"
    STATE_SCAN = "scan"
    STATE_DEPARTING = "departing"
    STATE_NAVIGATE = "navigate"
    STATE_VACUUM = "vacuum"
    STATE_STRAIN = "strain"
    STATE_RETURNING = "returning"
    STATE_DOCK_ALIGN = "dock_align"
    STATE_DOCK_REVERSE = "dock_reverse"
    STATE_EMPTYING = "emptying"

    # Remember dock position across overlay sessions
    SAVED_DOCK_POS: Optional[tuple[float, float]] = None

    def __init__(self, items: list[DesktopItem], mode: str = "clean", speed_multiplier: float = 1.0, dpr: float = 1.0):
        super().__init__()
        self.all_items = items
        self.eligible_items = [it for it in items if it.is_eligible]
        self.sucked_items: list[DesktopItem] = []
        self.mode = mode  # "tidy", "clean", "delete"
        self.speed_multiplier = speed_multiplier
        self.dpr = max(1.0, float(dpr))

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry()
        self.setGeometry(screen_geo)
        self.screen_w = screen_geo.width()
        self.screen_h = screen_geo.height()

        # Icon logical layout metrics
        self.icon_sz = 36.0

        # Vacuum and Dock dimensions
        self.vacuum_radius = 25.0
        self.vacuum_diameter = self.vacuum_radius * 2

        self.dock_w = 54
        self.dock_h = 82
        if OverlayWindow.SAVED_DOCK_POS is not None:
            self.dock_x, self.dock_y = OverlayWindow.SAVED_DOCK_POS
        else:
            self.dock_x = float(self.screen_w - 90)
            self.dock_y = float(self.screen_h - 68)

        # Resting position on dock: seated against disposal tower at bottom, facing North (into desktop)
        self.kuma_x = float(self.dock_x)
        self.kuma_y = float(self.dock_y - 10.0)
        self.kuma_angle = -math.pi * 0.5  # Facing North (out into desktop room)

        self.state = self.STATE_DOCK
        self.state_time = 0.0

        # Differential Drive Kinematics & Momentum (Calibrated to realistic robotic vacuum speeds)
        self.kuma_speed = 0.0          # Current forward linear speed (px/sec)
        self.max_cruise_speed = 78.0   # Calm, steady, realistic robot vacuum glide (px/sec)
        self.max_turn_speed = 2.0      # Deliberate differential chassis turn rate (rad/sec ~ 115 deg/sec)
        self.linear_accel = 100.0      # Gentle, weighted motor acceleration (px/sec^2)
        self.linear_decel = 150.0      # Smooth cushion braking (px/sec^2)
        self.bypass_waypoint: Optional[tuple[float, float]] = None

        # Robot grab state
        self.is_grabbed = False
        self.grab_offset_x = 0.0
        self.grab_offset_y = 0.0
        self.lift_height = 0.0
        self.wheel_spin_angle = 0.0

        # Dock grab and hover state (Movable dock)
        self.is_dock_grabbed = False
        self.dock_grab_offset_x = 0.0
        self.dock_grab_offset_y = 0.0
        self.dock_lift_height = 0.0
        self.is_dock_hovered = False

        self.lidar_angle = 0.0
        self.lidar_radius = 35.0
        self.lidar_max_radius = math.hypot(self.screen_w, self.screen_h) * 0.6
        self.locked_items: set[int] = set()

        self.current_target_index: Optional[int] = None
        self.suction_progress = 0.0
        self.strain_timer = 0.0
        self.shake_offset = QPointF(0, 0)

        # Dual side brushes & sensor
        self.side_brush_angle = 0.0
        self.laser_sensor_rot = 0.0
        self.particles: list[DebrisParticle] = []

        # Auto-empty station state & dust transfer animation
        self.empty_timer = 0.0
        self.empty_duration = 2.4
        self.dock_shake = QPointF(0, 0)
        self.empty_particles: list[dict] = []

        self._plan_cleaning_route()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.game_loop)
        self.last_tick = time.time()

    def get_dock_rect(self) -> QRectF:
        """Hit box for dock station grabbing and interaction."""
        w = float(self.dock_w)
        h = float(self.dock_h)
        return QRectF(
            self.dock_x - w / 2 - 10,
            self.dock_y - h / 2 - 10,
            w + 20,
            h + 20
        )

    def get_dock_approach_point(self) -> tuple[float, float]:
        """Dedicated access corridor portal in front of the dock entrance ramp (faces North into room)."""
        return (float(self.dock_x), float(self.dock_y - 70.0))

    def get_dock_obstacle_rect(self) -> QRectF:
        """Solid physical obstacle boundary of the dock station."""
        w = float(self.dock_w)
        h = float(self.dock_h)
        return QRectF(
            self.dock_x - w / 2 - 14,
            self.dock_y - h / 2 + 6,
            w + 28,
            h + 8
        )

    def _line_intersects_dock(self, p1: tuple[float, float], p2: tuple[float, float]) -> bool:
        """Check if line segment p1-p2 passes through the solid dock station boundary."""
        pad_x = self.dock_w * 0.5 + self.vacuum_radius + 4.0
        pad_y_top = self.dock_h * 0.5 - 6.0                      # Ramp mouth facing North into room
        pad_y_bot = self.dock_h * 0.5 + self.vacuum_radius + 4.0  # Disposal tower rear facing South (taskbar)

        left = self.dock_x - pad_x
        right = self.dock_x + pad_x
        top = self.dock_y - pad_y_top
        bottom = self.dock_y + pad_y_bot

        seg_min_x, seg_max_x = min(p1[0], p2[0]), max(p1[0], p2[0])
        seg_min_y, seg_max_y = min(p1[1], p2[1]), max(p1[1], p2[1])

        if seg_max_x < left or seg_min_x > right or seg_max_y < top or seg_min_y > bottom:
            return False

        # Liang-Barsky parametric line clipping
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        p = [-dx, dx, -dy, dy]
        q = [p1[0] - left, right - p1[0], p1[1] - top, bottom - p1[1]]

        u1, u2 = 0.0, 1.0
        for pi, qi in zip(p, q):
            if pi == 0:
                if qi < 0:
                    return False
            else:
                t = qi / pi
                if pi < 0:
                    if t > u2:
                        return False
                    if t > u1:
                        u1 = t
                else:
                    if t < u1:
                        return False
                    if t < u2:
                        u2 = t
        return u1 <= u2

    def _enforce_dock_collision(self):
        """Ensure the vacuum cannot penetrate solid dock station walls from any side."""
        if self.state in (self.STATE_DOCK, self.STATE_EMPTYING, self.STATE_DEPARTING, self.STATE_DOCK_REVERSE, self.STATE_DOCK_ALIGN):
            return
        if self.is_grabbed or self.is_dock_grabbed:
            return

        # Solid dock obstacle footprint (width 66, height 82, robot radius 26)
        pad_x = (self.dock_w * 0.5) + self.vacuum_radius - 2.0
        top_y = self.dock_y - (self.dock_h * 0.5) + 6.0
        bot_y = self.dock_y + (self.dock_h * 0.5) + self.vacuum_radius

        if abs(self.kuma_x - self.dock_x) < pad_x and top_y < self.kuma_y < bot_y:
            dx_left = self.kuma_x - (self.dock_x - pad_x)
            dx_right = (self.dock_x + pad_x) - self.kuma_x
            dy_bot = bot_y - self.kuma_y
            dy_top = self.kuma_y - top_y

            if dy_bot < dx_left and dy_bot < dx_right and self.kuma_y > self.dock_y:
                self.kuma_y = bot_y
            elif dy_top < dx_left and dy_top < dx_right and self.kuma_y < self.dock_y:
                self.kuma_y = top_y
            elif dx_left < dx_right:
                self.kuma_x = self.dock_x - pad_x
            else:
                self.kuma_x = self.dock_x + pad_x

            self.kuma_speed = max(0.0, self.kuma_speed * 0.3)

    def _plan_cleaning_route(self):
        """Greedy nearest-neighbor path to clean desktop in natural sweep."""
        if not self.eligible_items:
            return

        unvisited = list(range(len(self.eligible_items)))
        ordered = []
        cur_x, cur_y = self.kuma_x, self.kuma_y
        half_sz = self.icon_sz / 2

        while unvisited:
            best_idx = 0
            best_dist = float('inf')
            for i, item_idx in enumerate(unvisited):
                it = self.eligible_items[item_idx]
                d = math.hypot(it.x + half_sz - cur_x, it.y + half_sz - cur_y)
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            target_item_idx = unvisited.pop(best_idx)
            ordered.append(self.eligible_items[target_item_idx])
            cur_x = ordered[-1].x + half_sz
            cur_y = ordered[-1].y + half_sz

        self.eligible_items = ordered

    def showEvent(self, event):
        super().showEvent(event)
        self.last_tick = time.time()
        self.timer.start(16)
        self.state = self.STATE_DOCK
        self.state_time = 0.0

    def start_cleaning_sequence(self):
        if self.state != self.STATE_DOCK:
            return
        win32_helper.set_desktop_icons_visible(False)
        self.state = self.STATE_SCAN
        self.state_time = 0.0
        self.lidar_radius = 35.0
        self.locked_items.clear()
        sound_fx.play('ping', min_interval=0.12)

    def closeEvent(self, event):
        sound_fx.stop()
        win32_helper.set_desktop_icons_visible(True)
        self.timer.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            sound_fx.stop()
            win32_helper.set_desktop_icons_visible(True)
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            if self.state == self.STATE_DOCK:
                self.start_cleaning_sequence()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()

            # 1. Check HUD buttons
            w = 460
            h = 38
            x = (self.screen_w - w) / 2
            y = 18

            if self.state == self.STATE_DOCK:
                start_btn = QRectF(x + w - 195, y + 5, 110, 28)
                if start_btn.contains(pos):
                    self.start_cleaning_sequence()
                    return

                close_btn = QRectF(x + w - 76, y + 5, 68, 28)
                if close_btn.contains(pos):
                    sound_fx.stop()
                    win32_helper.set_desktop_icons_visible(True)
                    self.close()
                    return
            else:
                stop_btn = QRectF(x + w - 90, y + 5, 82, 28)
                if stop_btn.contains(pos):
                    sound_fx.stop()
                    win32_helper.set_desktop_icons_visible(True)
                    self.close()
                    return

            # 2. Check Dock vs Vacuum Interactivity (Draggable both when empty and with vacuum)
            dock_rect = self.get_dock_rect()
            dist_kuma = math.hypot(pos.x() - self.kuma_x, pos.y() - self.kuma_y)
            is_on_kuma = (dist_kuma <= self.vacuum_radius + 4)
            is_on_dock = dock_rect.contains(pos)

            if self.state in (self.STATE_DOCK, self.STATE_EMPTYING):
                # When robot is docked:
                # - Clicking on dock tower (lower portion near taskbar) or dock sides grabs the DOCK (moves dock + robot together)
                # - Clicking directly on robot lifts the robot off the dock
                if is_on_dock and (pos.y() > self.dock_y - 4 or not is_on_kuma):
                    self.is_dock_grabbed = True
                    self.dock_grab_offset_x = self.dock_x - pos.x()
                    self.dock_grab_offset_y = self.dock_y - pos.y()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    sound_fx.play('squeak')
                    self.update()
                    return
                elif is_on_kuma:
                    self.is_grabbed = True
                    self.grab_offset_x = self.kuma_x - pos.x()
                    self.grab_offset_y = self.kuma_y - pos.y()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    sound_fx.play('squeak')
                    self.update()
                    return
                elif is_on_dock:
                    self.is_dock_grabbed = True
                    self.dock_grab_offset_x = self.dock_x - pos.x()
                    self.dock_grab_offset_y = self.dock_y - pos.y()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    sound_fx.play('squeak')
                    self.update()
                    return
            else:
                # When robot is out cleaning (dock is empty):
                if is_on_dock:
                    self.is_dock_grabbed = True
                    self.dock_grab_offset_x = self.dock_x - pos.x()
                    self.dock_grab_offset_y = self.dock_y - pos.y()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    sound_fx.play('squeak')
                    self.update()
                    return
                elif is_on_kuma:
                    self.is_grabbed = True
                    self.grab_offset_x = self.kuma_x - pos.x()
                    self.grab_offset_y = self.kuma_y - pos.y()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    sound_fx.play('squeak')
                    self.update()
                    return

    def mouseMoveEvent(self, event):
        pos = event.position()

        # Handle Dock Dragging (empty or with vacuum)
        if self.is_dock_grabbed:
            new_x = pos.x() + self.dock_grab_offset_x
            new_y = pos.y() + self.dock_grab_offset_y

            margin_x = self.dock_w / 2 + 36
            margin_y_top = self.dock_h / 2 + 76.0
            margin_y_bottom = self.dock_h / 2 + 16.0

            self.dock_x = max(margin_x, min(self.screen_w - margin_x, new_x))
            self.dock_y = max(margin_y_top, min(self.screen_h - margin_y_bottom, new_y))

            OverlayWindow.SAVED_DOCK_POS = (self.dock_x, self.dock_y)

            # Move docked vacuum synchronously with dock
            if self.state in (self.STATE_DOCK, self.STATE_EMPTYING):
                self.kuma_x = float(self.dock_x)
                self.kuma_y = float(self.dock_y - 10.0)

            self.update()
            return

        # Handle Robot Vacuum Dragging
        if self.is_grabbed:
            self.kuma_x = pos.x() + self.grab_offset_x
            self.kuma_y = pos.y() + self.grab_offset_y
            self.update()
            return

        # Passive Hover Cursor Feedback
        dock_rect = self.get_dock_rect()
        dist_kuma = math.hypot(pos.x() - self.kuma_x, pos.y() - self.kuma_y)
        is_on_kuma = (dist_kuma <= self.vacuum_radius + 4)
        is_on_dock = dock_rect.contains(pos)

        old_hover = self.is_dock_hovered
        self.is_dock_hovered = is_on_dock

        if is_on_dock and (self.state != self.STATE_DOCK or pos.y() > self.dock_y - 4 or not is_on_kuma):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif is_on_kuma:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()

        if old_hover != self.is_dock_hovered:
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = self.is_dock_grabbed or self.is_grabbed

            if self.is_dock_grabbed:
                self.is_dock_grabbed = False
                OverlayWindow.SAVED_DOCK_POS = (self.dock_x, self.dock_y)

            if self.is_grabbed:
                self.is_grabbed = False
                # If released near the dock station, snap smoothly back onto the dock ramp!
                dist_to_dock = math.hypot(self.kuma_x - self.dock_x, self.kuma_y - (self.dock_y - 10.0))
                if dist_to_dock < 48.0:
                    self.kuma_x = float(self.dock_x)
                    self.kuma_y = float(self.dock_y - 10.0)
                    self.kuma_angle = -math.pi * 0.5
                    self.state = self.STATE_DOCK
                    sound_fx.play('pop')

            if was_dragging:
                self.unsetCursor()
                self.update()

    def game_loop(self):
        now = time.time()
        dt = (now - self.last_tick) * self.speed_multiplier
        self.last_tick = now
        self.state_time += dt

        brush_speed = 18.0 if self.state == self.STATE_VACUUM else (10.0 if self.state not in (self.STATE_DOCK, self.STATE_EMPTYING) else 0.0)
        self.side_brush_angle += dt * brush_speed
        self.laser_sensor_rot += dt * 12.0

        target_lift = 1.0 if self.is_grabbed else 0.0
        self.lift_height += (target_lift - self.lift_height) * min(1.0, dt * 10.0)
        if self.is_grabbed:
            self.wheel_spin_angle += dt * 22.0

        target_dock_lift = 1.0 if self.is_dock_grabbed else 0.0
        self.dock_lift_height += (target_dock_lift - self.dock_lift_height) * min(1.0, dt * 10.0)

        self.particles = [p for p in self.particles if p.update()]

        if self.is_grabbed or self.is_dock_grabbed:
            self.update()
            return

        if self.state == self.STATE_SCAN:
            self._update_scan(dt)
        elif self.state == self.STATE_DEPARTING:
            self._update_departing(dt)
        elif self.state == self.STATE_NAVIGATE:
            self._update_navigate(dt)
        elif self.state == self.STATE_VACUUM:
            self._update_vacuum(dt)
        elif self.state == self.STATE_STRAIN:
            self._update_strain(dt)
        elif self.state == self.STATE_RETURNING:
            self._update_returning(dt)
        elif self.state == self.STATE_DOCK_ALIGN:
            self._update_dock_align(dt)
        elif self.state == self.STATE_DOCK_REVERSE:
            self._update_dock_reverse(dt)
        elif self.state == self.STATE_EMPTYING:
            self._update_emptying(dt)

        # Solid dock collision barrier (cannot penetrate dock from any side)
        self._enforce_dock_collision()

        self.update()

    def _update_scan(self, dt: float):
        self.lidar_angle += dt * 6.0
        self.lidar_radius += dt * 450.0
        half_sz = self.icon_sz / 2

        for idx, item in enumerate(self.eligible_items):
            if idx not in self.locked_items:
                dist = math.hypot(item.x + half_sz - self.kuma_x, item.y + half_sz - self.kuma_y)
                if dist <= self.lidar_radius:
                    self.locked_items.add(idx)
                    sound_fx.play('ping', min_interval=0.10)

        if self.lidar_radius >= self.lidar_max_radius or self.state_time > 2.8:
            if self.eligible_items:
                self.state = self.STATE_DEPARTING
                self.current_target_index = 0
                self.kuma_speed = 0.0
            else:
                self.state = self.STATE_DOCK

    def _update_departing(self, dt: float):
        """Roll forward out of the dock ramp along the dedicated single-access corridor (North into room)."""
        approach_pt = self.get_dock_approach_point()
        self.kuma_angle = -math.pi * 0.5  # Facing North (out into desktop)
        self.kuma_x = float(self.dock_x)  # Locked to center corridor

        target_speed = 38.0  # Calm, steady roll out down the ramp
        self.kuma_speed = min(target_speed, self.kuma_speed + self.linear_accel * dt)
        self.kuma_y -= self.kuma_speed * dt
        self.wheel_spin_angle += self.kuma_speed * dt * 0.8

        if self.kuma_y <= approach_pt[1] + 8.0:
            # Corridor cleared! Transition to realistic differential-drive navigation
            self.state = self.STATE_NAVIGATE

    def _update_navigate(self, dt: float):
        """Realistic differential-drive kinematics with smooth acceleration, turning, and braking."""
        if self.current_target_index is None or self.current_target_index >= len(self.eligible_items):
            self.state = self.STATE_RETURNING
            self.bypass_waypoint = None
            return

        target = self.eligible_items[self.current_target_index]
        half_sz = self.icon_sz / 2
        tx = target.x + half_sz
        ty = target.y + half_sz

        # Dock obstacle avoidance: If heading passes through solid dock walls, route around exterior
        dest_x, dest_y = tx, ty
        if (self.kuma_y > self.dock_y - 35.0 and abs(self.kuma_x - self.dock_x) < 70.0) or \
           self._line_intersects_dock((self.kuma_x, self.kuma_y), (tx, ty)):
            side_x = self.dock_x - 74.0 if self.kuma_x < self.dock_x else self.dock_x + 74.0
            dest_x, dest_y = side_x, self.dock_y - 65.0

        dx = dest_x - self.kuma_x
        dy = dest_y - self.kuma_y
        dist = math.hypot(dx, dy)

        desired_angle = math.atan2(dy, dx)
        diff = (desired_angle - self.kuma_angle + math.pi) % (2 * math.pi) - math.pi

        # Steering dynamics: differential drive turns on spot for sharp angle, slows down
        if abs(diff) > math.radians(20):
            target_speed = 12.0
            turn_rate = min(abs(diff), self.max_turn_speed * dt)
            self.kuma_angle += math.copysign(turn_rate, diff)
            self.wheel_spin_angle += turn_rate * 6.0
        else:
            self.kuma_angle += diff * min(1.0, dt * 4.0)
            cos_align = max(0.2, math.cos(diff))
            if dist > 60.0:
                target_speed = self.max_cruise_speed * cos_align
            else:
                # Gentle braking deceleration as vacuum nears the target
                target_speed = max(18.0, self.max_cruise_speed * (dist / 60.0) * cos_align)

        # Smooth linear acceleration and braking
        if self.kuma_speed < target_speed:
            self.kuma_speed = min(target_speed, self.kuma_speed + self.linear_accel * dt)
        else:
            self.kuma_speed = max(target_speed, self.kuma_speed - self.linear_decel * dt)

        move_step = self.kuma_speed * dt
        self.kuma_x += math.cos(self.kuma_angle) * move_step
        self.kuma_y += math.sin(self.kuma_angle) * move_step
        self.wheel_spin_angle += self.kuma_speed * dt * 0.8

        # Target reached
        if dist <= 16.0:
            self.kuma_speed = 0.0
            self.state = self.STATE_VACUUM
            self.suction_progress = 0.0

    def _update_vacuum(self, dt: float):
        target = self.eligible_items[self.current_target_index]
        half_sz = self.icon_sz / 2
        tx = target.x + half_sz
        ty = target.y + half_sz

        mouth_x = self.kuma_x + math.cos(self.kuma_angle) * (self.vacuum_radius - 5)
        mouth_y = self.kuma_y + math.sin(self.kuma_angle) * (self.vacuum_radius - 5)

        for _ in range(3):
            self.particles.append(DebrisParticle(
                tx + random.uniform(-14, 14),
                ty + random.uniform(-14, 14),
                mouth_x,
                mouth_y
            ))

        self.suction_progress += dt * 2.6

        if self.suction_progress >= 1.0:
            sound_fx.play('pop')
            self.sucked_items.append(target)

            if target.is_heavy:
                self.state = self.STATE_STRAIN
                self.strain_timer = 1.4
                sound_fx.play('strain')
            else:
                self._next_target()

    def _update_strain(self, dt: float):
        self.strain_timer -= dt
        self.shake_offset = QPointF(
            random.uniform(-2.5, 2.5),
            random.uniform(-2.5, 2.5)
        )
        if self.strain_timer <= 0:
            self.shake_offset = QPointF(0, 0)
            self._next_target()

    def _next_target(self):
        self.current_target_index += 1
        if self.current_target_index < len(self.eligible_items):
            self.state = self.STATE_NAVIGATE
        else:
            self.state = self.STATE_RETURNING
            self.bypass_waypoint = None

    def _update_returning(self, dt: float):
        """Navigate to the front access point of the dock corridor (above dock), avoiding dock walls."""
        approach_pt = self.get_dock_approach_point()

        # Check if robot is currently behind or beside the dock, or heading through dock
        target_x, target_y = approach_pt
        if (self.kuma_y > self.dock_y - 35.0 and abs(self.kuma_x - self.dock_x) < 70.0) or \
           self._line_intersects_dock((self.kuma_x, self.kuma_y), approach_pt):
            side_x = self.dock_x - 74.0 if self.kuma_x < self.dock_x else self.dock_x + 74.0
            target_x, target_y = side_x, self.dock_y - 65.0

        dx = target_x - self.kuma_x
        dy = target_y - self.kuma_y
        dist = math.hypot(dx, dy)

        desired_angle = math.atan2(dy, dx)
        diff = (desired_angle - self.kuma_angle + math.pi) % (2 * math.pi) - math.pi

        if abs(diff) > math.radians(20):
            target_speed = 12.0
            turn_rate = min(abs(diff), self.max_turn_speed * dt)
            self.kuma_angle += math.copysign(turn_rate, diff)
            self.wheel_spin_angle += turn_rate * 6.0
        else:
            self.kuma_angle += diff * min(1.0, dt * 4.0)
            cos_align = max(0.2, math.cos(diff))
            if dist > 60.0:
                target_speed = self.max_cruise_speed * cos_align
            else:
                target_speed = max(18.0, self.max_cruise_speed * (dist / 60.0) * cos_align)

        if self.kuma_speed < target_speed:
            self.kuma_speed = min(target_speed, self.kuma_speed + self.linear_accel * dt)
        else:
            self.kuma_speed = max(target_speed, self.kuma_speed - self.linear_decel * dt)

        move_step = self.kuma_speed * dt
        self.kuma_x += math.cos(self.kuma_angle) * move_step
        self.kuma_y += math.sin(self.kuma_angle) * move_step
        self.wheel_spin_angle += self.kuma_speed * dt * 0.8

        # Arrived at the front access corridor waypoint!
        dist_to_portal = math.hypot(self.kuma_x - approach_pt[0], self.kuma_y - approach_pt[1])
        if dist_to_portal <= 8.0:
            self.kuma_speed = 0.0
            self.kuma_x = float(approach_pt[0])
            self.kuma_y = float(approach_pt[1])
            self.state = self.STATE_DOCK_ALIGN

    def _update_dock_align(self, dt: float):
        """Rotate on spot in front of dock corridor so rear faces South (into dock entrance)."""
        target_angle = -math.pi * 0.5  # Facing North (front pointing up, rear pointing down into ramp)
        diff = (target_angle - self.kuma_angle + math.pi) % (2 * math.pi) - math.pi

        turn_rate = min(abs(diff), self.max_turn_speed * dt * 0.75)
        self.kuma_angle += math.copysign(turn_rate, diff)
        self.wheel_spin_angle += turn_rate * 8.0

        if abs(diff) < math.radians(3.0):
            self.kuma_angle = -math.pi * 0.5
            self.state = self.STATE_DOCK_REVERSE
            sound_fx.play('squeak')

    def _update_dock_reverse(self, dt: float):
        """Reverse smoothly backwards down the dock ramp into charging contacts and waste tower."""
        self.kuma_x = float(self.dock_x)  # Locked along corridor centerline
        self.kuma_angle = -math.pi * 0.5  # Facing North (rear pointing South)

        reverse_speed = 22.0 * dt          # Slow, steady, realistic crawl backwards
        self.kuma_y += reverse_speed
        self.wheel_spin_angle -= dt * 6.0
        self.side_brush_angle -= dt * 1.5

        # Docking resting position reached (against disposal tower at bottom)
        if self.kuma_y >= self.dock_y - 10.0:
            self.kuma_y = float(self.dock_y - 10.0)
            sound_fx.play('pop')  # Latch click on contacts

            if self.sucked_items:
                self.state = self.STATE_EMPTYING
                self.empty_timer = 2.4 / max(0.5, self.speed_multiplier)
                self.empty_duration = self.empty_timer
                sound_fx.play('empty')
            else:
                self.state = self.STATE_DOCK
                self.timer.stop()
                sound_fx.play('victory')
                self.finished_cleaning.emit(self.sucked_items, self.mode)

    def _update_emptying(self, dt: float):
        self.empty_timer -= dt
        self.dock_shake = QPointF(
            random.uniform(-0.8, 0.8),
            random.uniform(-0.8, 0.8)
        )

        # Particle stream transferring from vacuum rear dustbin down into dock canister
        if random.random() < 0.75:
            for _ in range(2):
                self.empty_particles.append({
                    'x': self.kuma_x + random.uniform(-6, 6),
                    'y': self.kuma_y + 8,
                    'tx': self.dock_x + random.uniform(-4, 4),
                    'ty': self.dock_y + self.dock_h / 2 - 12,
                    'progress': 0.0,
                    'speed': random.uniform(2.0, 3.4),
                    'size': random.uniform(1.4, 2.8),
                    'color': QColor(
                        random.randint(180, 230),
                        random.randint(200, 240),
                        random.randint(220, 255)
                    )
                })

        alive = []
        for p in self.empty_particles:
            p['progress'] += dt * p['speed']
            if p['progress'] < 1.0:
                alive.append(p)
        self.empty_particles = alive

        if self.empty_timer <= 0:
            self.dock_shake = QPointF(0, 0)
            self.empty_particles.clear()
            self.state = self.STATE_DOCK
            sound_fx.stop()
            sound_fx.play('victory')
            self.timer.stop()
            self.finished_cleaning.emit(self.sucked_items, self.mode)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Dock Station
        self._draw_dock(painter)

        # Repositioning tag when dock is dragged
        if self.is_dock_grabbed:
            self._draw_dock_tag(painter, self.dock_x, self.dock_y - self.dock_h / 2 - 16)

        # 2. Emptying Dust Transfer Particles
        if self.state == self.STATE_EMPTYING:
            self._draw_empty_particles(painter)

        # 3. Desktop Icons (drawn during cleaning sequence)
        if self.state != self.STATE_DOCK:
            self._draw_desktop_icons(painter)

        # 4. LiDAR Sweep
        if self.state == self.STATE_SCAN:
            self._draw_lidar(painter)

        # 5. Debris Particles
        self._draw_particles(painter)

        # 6. Precision Vector Robot Vacuum
        self._draw_vacuum(painter)

        # 7. Minimalist Architectural HUD
        self._draw_hud(painter)

    def _draw_dock_tag(self, painter: QPainter, x: float, y: float):
        painter.save()
        font = QFont("Segoe UI", 8, QFont.Weight.Medium)
        painter.setFont(font)

        tag_rect = QRectF(x - 90, y - 20, 180, 22)
        painter.setPen(QPen(QColor(56, 189, 248, 180), 1))
        painter.setBrush(QBrush(QColor(16, 17, 22, 235)))
        painter.drawRoundedRect(tag_rect, 4, 4)

        painter.setPen(QColor(56, 189, 248))
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, "DOCKING STATION · MOVING")
        painter.restore()

    def _draw_dock(self, painter: QPainter):
        painter.save()
        lift_y = self.dock_lift_height * 5.0
        painter.translate(self.dock_x + self.dock_shake.x(), self.dock_y + self.dock_shake.y() - lift_y)

        w = self.dock_w
        h = self.dock_h

        # Ground contact shadow with dynamic elevation (centered under disposal tower at bottom)
        shadow_offset_y = 6.0 + self.dock_lift_height * 8.0
        shadow_scale = 1.0 + self.dock_lift_height * 0.18
        shadow_alpha = int(110 * (1.0 - self.dock_lift_height * 0.35))

        shadow = QRadialGradient(0, shadow_offset_y, w * 0.75 * shadow_scale)
        shadow.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
        shadow.setColorAt(0.6, QColor(0, 0, 0, int(shadow_alpha * 0.36)))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(-w * 0.65 * shadow_scale, -h * 0.35 + shadow_offset_y, w * 1.3 * shadow_scale, h * 0.95 * shadow_scale))

        # Dock ramp (Entrance mouth at top -Y facing North into desktop, away from taskbar)
        ramp_rect = QRectF(-w / 2, -h / 2, w, h - 20)
        ramp_grad = QLinearGradient(-w / 2, 0, w / 2, 0)
        ramp_grad.setColorAt(0.0, QColor(24, 25, 29))
        ramp_grad.setColorAt(0.5, QColor(32, 34, 40))
        ramp_grad.setColorAt(1.0, QColor(24, 25, 29))

        painter.setPen(QPen(QColor(48, 52, 60), 1))
        painter.setBrush(QBrush(ramp_grad))
        painter.drawRoundedRect(ramp_rect, 6, 6)

        # Solid side guide walls (Fenders) - single corridor entrance
        fender_w = 4.0
        fender_h = h - 22.0
        fender_y = -h / 2 + 2.0
        fender_grad = QLinearGradient(-w / 2, 0, -w / 2 + fender_w, 0)
        fender_grad.setColorAt(0.0, QColor(52, 56, 66))
        fender_grad.setColorAt(1.0, QColor(26, 28, 34))

        painter.setPen(QPen(QColor(65, 70, 82), 1.0))
        painter.setBrush(QBrush(fender_grad))
        # Left solid wall
        painter.drawRoundedRect(QRectF(-w / 2 - 1, fender_y, fender_w, fender_h), 2, 2)
        # Right solid wall
        painter.drawRoundedRect(QRectF(w / 2 - fender_w + 1, fender_y, fender_w, fender_h), 2, 2)

        # Tire alignment guide grooves
        painter.setPen(QPen(QColor(16, 17, 20), 1.5))
        painter.drawLine(int(-w * 0.32), int(-h / 2 + 6), int(-w * 0.32), int(h / 2 - 24))
        painter.drawLine(int(w * 0.32), int(-h / 2 + 6), int(w * 0.32), int(h / 2 - 24))

        # Brass charging contacts (located on ramp in front of disposal tower)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(212, 175, 55)))
        painter.drawRoundedRect(QRectF(-12, h / 2 - 27, 6, 3), 1, 1)
        painter.drawRoundedRect(QRectF(6, h / 2 - 27, 6, 3), 1, 1)

        # Vertical disposal tower (Tempat membuang sampah - Menghadap Taskbar di sisi bawah)
        tower_rect = QRectF(-w * 0.42, h / 2 - 26, w * 0.84, 26)
        tower_grad = QLinearGradient(0, h / 2 - 26, 0, h / 2)
        tower_grad.setColorAt(0.0, QColor(38, 41, 48))
        tower_grad.setColorAt(1.0, QColor(20, 21, 24))

        painter.setPen(QPen(QColor(60, 64, 74), 1))
        painter.setBrush(QBrush(tower_grad))
        painter.drawRoundedRect(tower_rect, 4, 4)

        # Tactile grip ridges on disposal tower
        painter.setPen(QPen(QColor(18, 19, 22), 1.0))
        painter.drawLine(int(-w * 0.22), int(h / 2 - 16), int(w * 0.22), int(h / 2 - 16))
        painter.drawLine(int(-w * 0.22), int(h / 2 - 12), int(w * 0.22), int(h / 2 - 12))

        # Hover accent line on tower rim
        if self.is_dock_hovered or self.is_dock_grabbed:
            painter.setPen(QPen(QColor(56, 189, 248, 180), 1.2))
            painter.drawLine(int(-w * 0.36), int(h / 2 - 25), int(w * 0.36), int(h / 2 - 25))

        # Suction channel glow when emptying
        if self.state == self.STATE_EMPTYING:
            suction_rect = QRectF(-w * 0.22, h / 2 - 25, w * 0.44, 22)
            channel_grad = QLinearGradient(0, h / 2 - 25, 0, h / 2)
            channel_grad.setColorAt(0.0, QColor(56, 189, 248, 110))
            channel_grad.setColorAt(0.5, QColor(245, 158, 11, 130))
            channel_grad.setColorAt(1.0, QColor(56, 189, 248, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(channel_grad))
            painter.drawRoundedRect(suction_rect, 4, 4)

        # Status pinhole LED
        if self.state == self.STATE_EMPTYING:
            led_color = QColor(245, 158, 11) if int(time.time() * 8) % 2 == 0 else QColor(56, 189, 248)
            pulse = 1.0
        elif self.state == self.STATE_DOCK:
            led_color = QColor(52, 211, 153)
            pulse = 0.8 + 0.2 * math.sin(time.time() * 3.5)
        else:
            led_color = QColor(96, 165, 250)
            pulse = 0.8 + 0.2 * math.sin(time.time() * 3.5)

        led_color.setAlpha(int(240 * pulse))
        painter.setBrush(QBrush(led_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, h / 2 - 7), 1.5, 1.5)

        painter.restore()

    def _draw_empty_particles(self, painter: QPainter):
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self.empty_particles:
            prog = p['progress']
            px = p['x'] * (1.0 - prog) + p['tx'] * prog + math.sin(prog * math.pi * 3) * 3.0
            py = p['y'] * (1.0 - prog) + p['ty'] * prog
            alpha = int(240 * math.sin(prog * math.pi))
            c = QColor(p['color'])
            c.setAlpha(max(0, min(255, alpha)))
            painter.setBrush(QBrush(c))
            painter.drawRect(QRectF(px, py, p['size'], p['size']))
        painter.restore()

    def _draw_desktop_icons(self, painter: QPainter):
        half_sz = self.icon_sz / 2
        for idx, item in enumerate(self.all_items):
            if item in self.sucked_items:
                continue

            is_current_target = (
                self.state in (self.STATE_VACUUM, self.STATE_STRAIN) and
                self.current_target_index is not None and
                idx < len(self.eligible_items) and
                self.eligible_items[self.current_target_index] == item
            )

            ix, iy = float(item.x), float(item.y)

            painter.save()

            if is_current_target:
                p = self.suction_progress
                mouth_x = self.kuma_x + math.cos(self.kuma_angle) * (self.vacuum_radius - 5)
                mouth_y = self.kuma_y + math.sin(self.kuma_angle) * (self.vacuum_radius - 5)

                ix = ix * (1.0 - p) + mouth_x * p
                iy = iy * (1.0 - p) + mouth_y * p
                scale = max(0.01, 1.0 - (p ** 1.8))

                painter.translate(ix + half_sz, iy + half_sz)
                painter.rotate(p * 180.0)
                painter.scale(scale, scale)
                painter.translate(-(ix + half_sz), -(iy + half_sz))

            # Target lock bracket ONLY on the active target item being vacuumed
            if is_current_target:
                painter.setPen(QPen(QColor(56, 189, 248, 160), 1.2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                cx, cy = ix + half_sz, iy + half_sz
                sz = half_sz + 4
                painter.drawLine(int(cx - sz), int(cy - sz), int(cx - sz + 6), int(cy - sz))
                painter.drawLine(int(cx - sz), int(cy - sz), int(cx - sz), int(cy - sz + 6))
                painter.drawLine(int(cx + sz), int(cy - sz), int(cx + sz - 6), int(cy - sz))
                painter.drawLine(int(cx + sz), int(cy - sz), int(cx + sz), int(cy - sz + 6))
                painter.drawLine(int(cx - sz), int(cy + sz), int(cx - sz + 6), int(cy + sz))
                painter.drawLine(int(cx - sz), int(cy + sz), int(cx - sz), int(cy + sz - 6))
                painter.drawLine(int(cx + sz), int(cy + sz), int(cx + sz - 6), int(cy + sz))
                painter.drawLine(int(cx + sz), int(cy + sz), int(cx + sz), int(cy + sz - 6))

            # Icon Image
            if item.pixmap:
                pix_rect = QRectF(ix, iy, self.icon_sz, self.icon_sz)
                painter.drawPixmap(pix_rect.toRect(), item.pixmap)
            else:
                painter.setBrush(QBrush(QColor(40, 44, 52)))
                painter.setPen(QPen(QColor(70, 75, 85), 1))
                painter.drawRoundedRect(int(ix + 2), int(iy + 2), int(self.icon_sz - 4), int(self.icon_sz - 4), 4, 4)

            # Native Windows Desktop Icon Label Rendering:
            # Transparent background (NO ugly black background box!)
            # 1px soft drop shadow for readability over wallpaper, crisp white text.
            if not is_current_target:
                cx = ix + half_sz
                label_w = 74.0
                label_h = 32.0
                text_rect = QRectF(cx - label_w / 2, iy + self.icon_sz + 2, label_w, label_h)

                font = QFont("Segoe UI", 8)
                font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
                painter.setFont(font)

                display_text = item.display_name or item.name

                # 1px Drop Shadow
                shadow_rect = QRectF(text_rect.x() + 1, text_rect.y() + 1, text_rect.width(), text_rect.height())
                painter.setPen(QColor(0, 0, 0, 185))
                painter.drawText(
                    shadow_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                    display_text
                )

                # Pure white label text
                painter.setPen(QColor(255, 255, 255, 245))
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                    display_text
                )

            painter.restore()

    def _draw_lidar(self, painter: QPainter):
        painter.save()
        pen = QPen(QColor(96, 165, 250, 110), 1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(self.kuma_x, self.kuma_y), self.lidar_radius, self.lidar_radius)

        cone_grad = QRadialGradient(self.kuma_x, self.kuma_y, self.lidar_radius)
        cone_grad.setColorAt(0.0, QColor(96, 165, 250, 90))
        cone_grad.setColorAt(1.0, QColor(96, 165, 250, 0))

        painter.setBrush(QBrush(cone_grad))
        painter.setPen(Qt.PenStyle.NoPen)

        span = 24.0
        start_deg = math.degrees(self.lidar_angle) - span / 2
        rect = QRectF(
            self.kuma_x - self.lidar_radius,
            self.kuma_y - self.lidar_radius,
            self.lidar_radius * 2,
            self.lidar_radius * 2
        )
        painter.drawPie(rect, int(start_deg * 16), int(span * 16))
        painter.restore()

    def _draw_particles(self, painter: QPainter):
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        for p in self.particles:
            c = QColor(p.color)
            c.setAlpha(int(220 * p.life))
            painter.setBrush(QBrush(c))
            painter.drawRect(QRectF(p.x, p.y, p.w, p.h))
        painter.restore()

    def _draw_vacuum(self, painter: QPainter):
        painter.save()

        pos_x = self.kuma_x + self.shake_offset.x()
        pos_y = self.kuma_y + self.shake_offset.y()
        # If parked on dock, lift synchronously with the dock
        if self.state in (self.STATE_DOCK, self.STATE_EMPTYING) and not self.is_grabbed:
            pos_y -= self.dock_lift_height * 5.0

        r = self.vacuum_radius

        # Drop shadow beneath chassis
        shadow_offset_y = 3.0 + self.lift_height * 14.0
        shadow_scale = 1.0 + self.lift_height * 0.25
        shadow_alpha = int(120 * (1.0 - self.lift_height * 0.4))

        shadow_grad = QRadialGradient(pos_x, pos_y + shadow_offset_y, (r + 4) * shadow_scale)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
        shadow_grad.setColorAt(0.65, QColor(0, 0, 0, int(shadow_alpha * 0.35)))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow_grad))
        painter.drawEllipse(
            QPointF(pos_x, pos_y + shadow_offset_y),
            (r + 4) * shadow_scale,
            (r + 2) * shadow_scale
        )

        painter.translate(pos_x, pos_y)
        painter.rotate(math.degrees(self.kuma_angle) + 90)

        # Wheels if picked up
        if self.lift_height > 0.05:
            self._draw_wheels(painter, r)

        # DUAL FRONT SIDE BRUSHES (Underside mounted, drawn BEFORE chassis so roots are under the hood!)
        self._draw_side_brushes(painter, r)

        # Main Chassis Body (drawn ON TOP of brushes so brushes emerge from underneath the rim)
        chassis_grad = QLinearGradient(-r * 0.7, -r * 0.7, r * 0.7, r * 0.7)
        chassis_grad.setColorAt(0.0, QColor(42, 45, 52))
        chassis_grad.setColorAt(0.5, QColor(24, 25, 29))
        chassis_grad.setColorAt(1.0, QColor(16, 17, 20))

        painter.setPen(QPen(QColor(55, 58, 68), 1.2))
        painter.setBrush(QBrush(chassis_grad))
        painter.drawEllipse(QPointF(0, 0), r, r)

        # Front Mechanical Bumper
        painter.setPen(QPen(QColor(14, 15, 17), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(-r + 1.5, -r + 1.5, (r - 1.5) * 2, (r - 1.5) * 2), int(10 * 16), int(160 * 16))

        # Optical window on front bumper
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(12, 13, 16)))
        painter.drawRoundedRect(QRectF(-8, -r + 1.5, 16, 2.5), 1, 1)

        # Dustbin Hood Seam
        painter.setPen(QPen(QColor(36, 38, 44), 1.0))
        painter.drawArc(QRectF(-r * 0.8, -r * 0.8, r * 1.6, r * 1.6), int(200 * 16), int(140 * 16))

        # Raised LDS LiDAR Turret
        turret_r = 7.5
        turret_shadow = QRadialGradient(0.5, 1.5, turret_r + 2)
        turret_shadow.setColorAt(0.0, QColor(0, 0, 0, 160))
        turret_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(turret_shadow))
        painter.drawEllipse(QPointF(0.5, 1.5), turret_r + 1.5, turret_r + 1.5)

        turret_grad = QLinearGradient(-turret_r, -turret_r, turret_r, turret_r)
        turret_grad.setColorAt(0.0, QColor(75, 78, 88))
        turret_grad.setColorAt(0.5, QColor(35, 37, 43))
        turret_grad.setColorAt(1.0, QColor(20, 21, 25))

        painter.setPen(QPen(QColor(85, 88, 100), 1.0))
        painter.setBrush(QBrush(turret_grad))
        painter.drawEllipse(QPointF(0, 0), turret_r, turret_r)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(10, 11, 13)))
        painter.drawEllipse(QPointF(0, 0), turret_r - 2.0, turret_r - 2.0)

        # Rotating laser sensor diode
        if self.state not in (self.STATE_DOCK, self.STATE_EMPTYING):
            sensor_x = math.cos(self.laser_sensor_rot) * 3.5
            sensor_y = math.sin(self.laser_sensor_rot) * 3.5
            painter.setBrush(QBrush(QColor(239, 68, 68)))
            painter.drawEllipse(QPointF(sensor_x, sensor_y), 1.2, 1.2)

        painter.setPen(QPen(QColor(50, 53, 62), 0.8))
        painter.setBrush(QBrush(QColor(26, 28, 33)))
        painter.drawEllipse(QPointF(0, 0), turret_r - 3.2, turret_r - 3.2)

        # LED status ring
        led_color = QColor(52, 211, 153) if self.state == self.STATE_DOCK else QColor(96, 165, 250)
        if self.state == self.STATE_STRAIN:
            led_color = QColor(239, 68, 68)
        elif self.state == self.STATE_EMPTYING:
            led_color = QColor(245, 158, 11)
        elif self.is_grabbed:
            led_color = QColor(245, 158, 11)

        pulse = 0.8 + 0.2 * math.sin(time.time() * 4.0)
        led_color.setAlpha(int(240 * pulse))
        painter.setBrush(QBrush(led_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, -r * 0.58), 1.6, 1.6)

        painter.restore()

        if self.is_grabbed:
            self._draw_lift_tag(painter, pos_x, pos_y - r - 18)

    def _draw_side_brushes(self, painter: QPainter, r: float):
        """
        Dual front side brushes mounted on the underside.
        Drawn BEFORE the chassis so only the protruding bristles emerge from under the rim.
        """
        # Underside front-left and front-right mounting hubs
        brushes = [
            (-r * 0.70, -r * 0.60, 1.0),   # Left brush, clockwise sweep
            (r * 0.70, -r * 0.60, -1.0),   # Right brush, counter-clockwise sweep
        ]

        arm_len = 15.5  # Enlarged bristle arm reach

        for bx, by, rot_sign in brushes:
            painter.save()
            painter.translate(bx, by)
            painter.rotate(math.degrees(self.side_brush_angle * rot_sign))

            # Ground drop shadow for protruding bristles
            painter.setPen(QPen(QColor(0, 0, 0, 85), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for i in range(3):
                arm_angle = i * (math.pi * 2 / 3)
                ax = math.cos(arm_angle) * arm_len
                ay = math.sin(arm_angle) * arm_len + 1.2
                painter.drawLine(0, 1, int(ax), int(ay))

            # Primary flexible nylon bristle arms
            painter.setPen(QPen(QColor(225, 228, 236), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for i in range(3):
                arm_angle = i * (math.pi * 2 / 3)
                ax = math.cos(arm_angle) * arm_len
                ay = math.sin(arm_angle) * arm_len
                painter.drawLine(0, 0, int(ax), int(ay))

                # Bristle tuft tip spread for realistic sweep appearance
                tip_a1 = arm_angle + 0.22
                tip_a2 = arm_angle - 0.22
                painter.drawLine(
                    int(ax), int(ay),
                    int(ax + math.cos(tip_a1) * 3.5),
                    int(ay + math.sin(tip_a1) * 3.5)
                )
                painter.drawLine(
                    int(ax), int(ay),
                    int(ax + math.cos(tip_a2) * 3.5),
                    int(ay + math.sin(tip_a2) * 3.5)
                )

            # Underside brush hub pivot
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(24, 26, 30)))
            painter.drawEllipse(QPointF(0, 0), 2.8, 2.8)
            painter.restore()

    def _draw_wheels(self, painter: QPainter, r: float):
        painter.save()
        ext = self.lift_height * 5.0
        for side in [-1, 1]:
            wx = side * (r + ext - 2)
            wy = 0.0

            painter.setPen(QPen(QColor(150, 155, 168), 1.2))
            painter.drawLine(int(side * (r - 4)), int(wy), int(wx), int(wy))

            painter.save()
            painter.translate(wx, wy)
            painter.rotate(math.degrees(self.wheel_spin_angle))
            painter.setPen(QPen(QColor(18, 19, 22), 1.0))
            painter.setBrush(QBrush(QColor(38, 40, 48)))
            painter.drawRoundedRect(-3, -7, 6, 14, 1.5, 1.5)
            painter.restore()
        painter.restore()

    def _draw_lift_tag(self, painter: QPainter, x: float, y: float):
        painter.save()
        font = QFont("Segoe UI", 8, QFont.Weight.Medium)
        painter.setFont(font)

        tag_rect = QRectF(x - 90, y - 20, 180, 22)
        painter.setPen(QPen(QColor(60, 64, 75), 1))
        painter.setBrush(QBrush(QColor(18, 19, 23, 230)))
        painter.drawRoundedRect(tag_rect, 4, 4)

        painter.setPen(QColor(245, 158, 11))
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, "WHEELS SUSPENDED")
        painter.restore()

    def _draw_hud(self, painter: QPainter):
        painter.save()
        w = 460
        h = 38
        x = (self.screen_w - w) / 2
        y = 18

        hud_rect = QRectF(x, y, w, h)
        painter.setPen(QPen(QColor(48, 52, 62, 220), 1))
        painter.setBrush(QBrush(QColor(16, 17, 21, 235)))
        painter.drawRoundedRect(hud_rect, 19, 19)

        font_label = QFont("Segoe UI", 9, QFont.Weight.Medium)
        painter.setFont(font_label)

        mode_titles = {
            "tidy": "Tidy Up",
            "clean": "Clean",
            "delete": "Delete"
        }
        mode_str = mode_titles.get(self.mode, "Clean")

        if self.state == self.STATE_DOCK:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(52, 211, 153)))
            painter.drawEllipse(QPointF(x + 20, y + h / 2), 3.5, 3.5)

            painter.setPen(QColor(220, 224, 234))
            painter.drawText(QRectF(x + 32, y, 210, h), Qt.AlignmentFlag.AlignVCenter, f"Kuma LDS  ·  {mode_str}  ·  Ready")

            start_btn = QRectF(x + w - 195, y + 5, 110, 28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(240, 242, 248)))
            painter.drawRoundedRect(start_btn, 14, 14)

            btn_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            painter.setFont(btn_font)
            painter.setPen(QColor(15, 16, 20))
            painter.drawText(start_btn, Qt.AlignmentFlag.AlignCenter, f"{mode_str} (Space)")

            close_btn = QRectF(x + w - 76, y + 5, 68, 28)
            painter.setBrush(QBrush(QColor(30, 32, 38)))
            painter.setPen(QPen(QColor(50, 54, 64), 1))
            painter.drawRoundedRect(close_btn, 14, 14)
            painter.setPen(QColor(160, 166, 180))
            painter.setFont(font_label)
            painter.drawText(close_btn, Qt.AlignmentFlag.AlignCenter, "Close")

        else:
            state_text_map = {
                self.STATE_SCAN: "Scanning desktop with LDS LiDAR...",
                self.STATE_DEPARTING: "Departing dock corridor...",
                self.STATE_NAVIGATE: f"{mode_str} · {len(self.sucked_items)} of {len(self.eligible_items)}",
                self.STATE_VACUUM: "Vacuuming item...",
                self.STATE_STRAIN: "High-density item...",
                self.STATE_RETURNING: "Returning to dock corridor...",
                self.STATE_DOCK_ALIGN: "Aligning for dock approach...",
                self.STATE_DOCK_REVERSE: "Docking in reverse...",
                self.STATE_EMPTYING: "Auto-Emptying Station · Transferring to dock...",
            }
            status_text = state_text_map.get(self.state, "In progress")

            pulse_color = QColor(96, 165, 250)
            if self.state == self.STATE_STRAIN:
                pulse_color = QColor(239, 68, 68)
            elif self.state in (self.STATE_DOCK_REVERSE, self.STATE_DOCK_ALIGN):
                pulse_color = QColor(56, 189, 248)
            elif self.state == self.STATE_EMPTYING:
                pulse_color = QColor(245, 158, 11)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pulse_color))
            painter.drawEllipse(QPointF(x + 20, y + h / 2), 3.5, 3.5)

            painter.setPen(QColor(220, 224, 234))
            painter.drawText(QRectF(x + 32, y, 290, h), Qt.AlignmentFlag.AlignVCenter, f"Kuma LDS  ·  {status_text}")

            # Progress bar for emptying
            if self.state == self.STATE_EMPTYING:
                p = max(0.0, min(1.0, 1.0 - (self.empty_timer / max(0.1, self.empty_duration))))
                bar_rect = QRectF(x + 32, y + h - 5, (w - 140) * p, 2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(56, 189, 248)))
                painter.drawRoundedRect(bar_rect, 1, 1)

            stop_btn = QRectF(x + w - 90, y + 5, 82, 28)
            painter.setBrush(QBrush(QColor(36, 38, 46)))
            painter.setPen(QPen(QColor(60, 64, 76), 1))
            painter.drawRoundedRect(stop_btn, 14, 14)
            painter.setPen(QColor(220, 224, 234))
            painter.setFont(font_label)
            painter.drawText(stop_btn, Qt.AlignmentFlag.AlignCenter, "Cancel")

        painter.restore()
