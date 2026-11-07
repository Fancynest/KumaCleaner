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
    """Realistic physical desktop dust/lint particle (desaturated, micro-scale)."""
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
        # Realistic muted debris colors (dust grey, paper fleck, lint)
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
    finished_cleaning = pyqtSignal(list)

    STATE_DOCK = "dock"
    STATE_SCAN = "scan"
    STATE_NAVIGATE = "navigate"
    STATE_VACUUM = "vacuum"
    STATE_STRAIN = "strain"
    STATE_RETURNING = "returning"

    def __init__(self, items: list[DesktopItem], speed_multiplier: float = 1.0):
        super().__init__()
        self.all_items = items
        self.eligible_items = [it for it in items if it.is_eligible]
        self.sucked_items: list[DesktopItem] = []
        self.speed_multiplier = speed_multiplier

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

        # Proportional, realistic physical scale
        self.vacuum_radius = 25.0  # 50px diameter (compact desktop companion)
        self.vacuum_diameter = self.vacuum_radius * 2

        self.dock_w = 54
        self.dock_h = 82
        self.dock_x = self.screen_w - 90
        self.dock_y = self.screen_h - 105

        # Resting position on dock
        self.kuma_x = float(self.dock_x)
        self.kuma_y = float(self.dock_y + 12)
        self.kuma_angle = -math.pi * 0.5  # Facing north

        self.state = self.STATE_DOCK
        self.state_time = 0.0

        # Physical suspension & kinematics
        self.is_grabbed = False
        self.grab_offset_x = 0.0
        self.grab_offset_y = 0.0
        self.lift_height = 0.0
        self.wheel_spin_angle = 0.0

        # LiDAR scanning variables
        self.lidar_angle = 0.0
        self.lidar_radius = 35.0
        self.lidar_max_radius = math.hypot(self.screen_w, self.screen_h) * 0.6
        self.locked_items: set[int] = set()

        self.current_target_index: Optional[int] = None
        self.suction_progress = 0.0
        self.strain_timer = 0.0
        self.shake_offset = QPointF(0, 0)

        self.side_brush_angle = 0.0
        self.laser_sensor_rot = 0.0
        self.particles: list[DebrisParticle] = []

        self._plan_cleaning_route()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.game_loop)
        self.last_tick = time.time()

        win32_helper.set_desktop_icons_visible(True)

    def _plan_cleaning_route(self):
        if not self.eligible_items:
            return

        unvisited = list(range(len(self.eligible_items)))
        ordered = []
        cur_x, cur_y = self.dock_x, self.dock_y

        while unvisited:
            best_idx = 0
            best_dist = float('inf')
            for i, item_idx in enumerate(unvisited):
                it = self.eligible_items[item_idx]
                d = math.hypot(it.x + 24 - cur_x, it.y + 24 - cur_y)
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            target_item_idx = unvisited.pop(best_idx)
            ordered.append(self.eligible_items[target_item_idx])
            cur_x = ordered[-1].x + 24
            cur_y = ordered[-1].y + 24

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
        sound_fx.play('ping')

    def closeEvent(self, event):
        win32_helper.set_desktop_icons_visible(True)
        self.timer.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            win32_helper.set_desktop_icons_visible(True)
            self.close()
        elif event.key() == Qt.Key.Key_Space:
            if self.state == self.STATE_DOCK:
                self.start_cleaning_sequence()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            dist = math.hypot(pos.x() - self.kuma_x, pos.y() - self.kuma_y)
            if dist <= self.vacuum_radius + 10:
                self.is_grabbed = True
                self.grab_offset_x = self.kuma_x - pos.x()
                self.grab_offset_y = self.kuma_y - pos.y()
                sound_fx.play('squeak')
                self.update()
                return

            w = 420
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
                    win32_helper.set_desktop_icons_visible(True)
                    self.close()
                    return
            else:
                stop_btn = QRectF(x + w - 90, y + 5, 82, 28)
                if stop_btn.contains(pos):
                    win32_helper.set_desktop_icons_visible(True)
                    self.close()
                    return

    def mouseMoveEvent(self, event):
        if self.is_grabbed:
            pos = event.position()
            self.kuma_x = pos.x() + self.grab_offset_x
            self.kuma_y = pos.y() + self.grab_offset_y
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_grabbed:
            self.is_grabbed = False
            self.update()

    def game_loop(self):
        now = time.time()
        dt = (now - self.last_tick) * self.speed_multiplier
        self.last_tick = now
        self.state_time += dt

        brush_speed = 18.0 if self.state == self.STATE_VACUUM else (10.0 if self.state != self.STATE_DOCK else 0.0)
        self.side_brush_angle += dt * brush_speed
        self.laser_sensor_rot += dt * 12.0

        target_lift = 1.0 if self.is_grabbed else 0.0
        self.lift_height += (target_lift - self.lift_height) * min(1.0, dt * 10.0)
        if self.is_grabbed:
            self.wheel_spin_angle += dt * 22.0

        self.particles = [p for p in self.particles if p.update()]

        if self.is_grabbed:
            self.update()
            return

        if self.state == self.STATE_SCAN:
            self._update_scan(dt)
        elif self.state == self.STATE_NAVIGATE:
            self._update_navigate(dt)
        elif self.state == self.STATE_VACUUM:
            self._update_vacuum(dt)
        elif self.state == self.STATE_STRAIN:
            self._update_strain(dt)
        elif self.state == self.STATE_RETURNING:
            self._update_returning(dt)

        self.update()

    def _update_scan(self, dt: float):
        self.lidar_angle += dt * 6.0
        self.lidar_radius += dt * 450.0

        for idx, item in enumerate(self.eligible_items):
            if idx not in self.locked_items:
                dist = math.hypot(item.x + 24 - self.kuma_x, item.y + 24 - self.kuma_y)
                if dist <= self.lidar_radius:
                    self.locked_items.add(idx)
                    sound_fx.play('ping')

        if self.lidar_radius >= self.lidar_max_radius or self.state_time > 2.8:
            if self.eligible_items:
                self.state = self.STATE_NAVIGATE
                self.current_target_index = 0
            else:
                self.state = self.STATE_RETURNING

    def _update_navigate(self, dt: float):
        if self.current_target_index is None or self.current_target_index >= len(self.eligible_items):
            self.state = self.STATE_RETURNING
            sound_fx.play('victory')
            return

        target = self.eligible_items[self.current_target_index]
        tx = target.x + 24
        ty = target.y + 24

        dx = tx - self.kuma_x
        dy = ty - self.kuma_y
        dist = math.hypot(dx, dy)

        desired_angle = math.atan2(dy, dx)
        diff = (desired_angle - self.kuma_angle + math.pi) % (2 * math.pi) - math.pi
        self.kuma_angle += diff * min(1.0, dt * 8.5)

        speed = 260.0 * dt
        if dist > 18:
            self.kuma_x += math.cos(self.kuma_angle) * min(dist, speed)
            self.kuma_y += math.sin(self.kuma_angle) * min(dist, speed)
        else:
            self.state = self.STATE_VACUUM
            self.suction_progress = 0.0

    def _update_vacuum(self, dt: float):
        target = self.eligible_items[self.current_target_index]
        tx = target.x + 24
        ty = target.y + 24

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
            sound_fx.play('victory')

    def _update_returning(self, dt: float):
        target_dock_x = self.dock_x
        target_dock_y = self.dock_y + 12

        dx = target_dock_x - self.kuma_x
        dy = target_dock_y - self.kuma_y
        dist = math.hypot(dx, dy)

        desired_angle = math.atan2(dy, dx)
        diff = (desired_angle - self.kuma_angle + math.pi) % (2 * math.pi) - math.pi
        self.kuma_angle += diff * min(1.0, dt * 7.0)

        speed = 280.0 * dt
        if dist > 8:
            self.kuma_x += math.cos(self.kuma_angle) * min(dist, speed)
            self.kuma_y += math.sin(self.kuma_angle) * min(dist, speed)
        else:
            self.kuma_angle = -math.pi * 0.5
            self.state = self.STATE_DOCK
            self.timer.stop()
            self.finished_cleaning.emit(self.sucked_items)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Dock Station
        self._draw_dock(painter)

        # 2. Desktop Icons (during cleaning sequence)
        if self.state != self.STATE_DOCK:
            self._draw_desktop_icons(painter)

        # 3. LiDAR Sweep
        if self.state == self.STATE_SCAN:
            self._draw_lidar(painter)

        # 4. Physical Debris Particles
        self._draw_particles(painter)

        # 5. Precision Vector Robot Vacuum
        self._draw_vacuum(painter)

        # 6. Minimalist Architectural HUD
        self._draw_hud(painter)

    def _draw_dock(self, painter: QPainter):
        """Precision architectural rendering of modern auto-empty base."""
        painter.save()
        painter.translate(self.dock_x, self.dock_y)

        w = self.dock_w
        h = self.dock_h

        # Diffused contact shadow
        shadow = QRadialGradient(0, 10, w * 0.75)
        shadow.setColorAt(0.0, QColor(0, 0, 0, 110))
        shadow.setColorAt(0.6, QColor(0, 0, 0, 40))
        shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(-w * 0.65, -h * 0.45, w * 1.3, h * 1.05))

        # Base ramp (Matte Dark Graphite with subtle surface gradient)
        ramp_rect = QRectF(-w / 2, -h / 2 + 20, w, h - 20)
        ramp_grad = QLinearGradient(-w / 2, 0, w / 2, 0)
        ramp_grad.setColorAt(0.0, QColor(24, 25, 29))
        ramp_grad.setColorAt(0.5, QColor(32, 34, 40))
        ramp_grad.setColorAt(1.0, QColor(24, 25, 29))

        painter.setPen(QPen(QColor(48, 52, 60), 1))
        painter.setBrush(QBrush(ramp_grad))
        painter.drawRoundedRect(ramp_rect, 6, 6)

        # Wheel guide grooves
        painter.setPen(QPen(QColor(16, 17, 20), 1.5))
        painter.drawLine(int(-w * 0.32), int(-h / 2 + 28), int(-w * 0.32), int(h / 2 - 6))
        painter.drawLine(int(w * 0.32), int(-h / 2 + 28), int(w * 0.32), int(h / 2 - 6))

        # Precision brass charging contacts
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(212, 175, 55)))  # Satin brass
        painter.drawRoundedRect(QRectF(-12, -h / 2 + 24, 6, 3), 1, 1)
        painter.drawRoundedRect(QRectF(6, -h / 2 + 24, 6, 3), 1, 1)

        # Vertical Tower Body
        tower_rect = QRectF(-w * 0.42, -h / 2, w * 0.84, 26)
        tower_grad = QLinearGradient(0, -h / 2, 0, -h / 2 + 26)
        tower_grad.setColorAt(0.0, QColor(38, 41, 48))
        tower_grad.setColorAt(1.0, QColor(20, 21, 24))

        painter.setPen(QPen(QColor(60, 64, 74), 1))
        painter.setBrush(QBrush(tower_grad))
        painter.drawRoundedRect(tower_rect, 4, 4)

        # Single micro status LED pinhole
        led_color = QColor(52, 211, 153) if self.state == self.STATE_DOCK else QColor(96, 165, 250)
        pulse = 0.8 + 0.2 * math.sin(time.time() * 3.5)
        led_color.setAlpha(int(240 * pulse))
        painter.setBrush(QBrush(led_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, -h / 2 + 7), 1.5, 1.5)

        painter.restore()

    def _draw_desktop_icons(self, painter: QPainter):
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

                painter.translate(ix + 24, iy + 24)
                painter.rotate(p * 180.0)
                painter.scale(scale, scale)
                painter.translate(-(ix + 24), -(iy + 24))

            # Minimalist target brackets
            if item.is_eligible and idx in self.locked_items and not is_current_target:
                painter.setPen(QPen(QColor(96, 165, 250, 140), 1.2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                cx, cy = ix + 24, iy + 24
                sz = 24
                # Corner ticks
                painter.drawLine(int(cx - sz), int(cy - sz), int(cx - sz + 6), int(cy - sz))
                painter.drawLine(int(cx - sz), int(cy - sz), int(cx - sz), int(cy - sz + 6))
                painter.drawLine(int(cx + sz), int(cy - sz), int(cx + sz - 6), int(cy - sz))
                painter.drawLine(int(cx + sz), int(cy - sz), int(cx + sz), int(cy - sz + 6))
                painter.drawLine(int(cx - sz), int(cy + sz), int(cx - sz + 6), int(cy + sz))
                painter.drawLine(int(cx - sz), int(cy + sz), int(cx - sz), int(cy + sz - 6))
                painter.drawLine(int(cx + sz), int(cy + sz), int(cx + sz - 6), int(cy + sz))
                painter.drawLine(int(cx + sz), int(cy + sz), int(cx + sz), int(cy + sz - 6))

            if item.pixmap:
                painter.drawPixmap(int(ix), int(iy), item.pixmap)
            else:
                painter.setBrush(QBrush(QColor(40, 44, 52)))
                painter.setPen(QPen(QColor(70, 75, 85), 1))
                painter.drawRoundedRect(int(ix + 4), int(iy + 4), 40, 40, 4, 4)

            if not is_current_target:
                font = QFont("Segoe UI", 9)
                painter.setFont(font)

                display_text = item.name
                if len(display_text) > 16:
                    display_text = display_text[:14] + ".."

                text_rect = QRectF(ix - 15, iy + 50, 78, 20)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(15, 16, 20, 210)))
                painter.drawRoundedRect(text_rect, 3, 3)

                painter.setPen(QColor(230, 232, 238))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, display_text)

            painter.restore()

    def _draw_lidar(self, painter: QPainter):
        painter.save()
        # Subtle, precise radar pulse
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
        """Precision vector CAD rendering of a modern robot vacuum cleaner."""
        painter.save()

        pos_x = self.kuma_x + self.shake_offset.x()
        pos_y = self.kuma_y + self.shake_offset.y()
        r = self.vacuum_radius

        # 1. Soft Physical Ambient Occlusion Shadow
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

        # 2. Local Frame Transformation
        painter.translate(pos_x, pos_y)
        painter.rotate(math.degrees(self.kuma_angle) + 90)

        # 3. Suspended Wheels (if lifted)
        if self.lift_height > 0.05:
            self._draw_wheels(painter, r)

        # 4. Main Chassis Base (Matte PBT Composite with 45° Key Lighting)
        chassis_grad = QLinearGradient(-r * 0.7, -r * 0.7, r * 0.7, r * 0.7)
        chassis_grad.setColorAt(0.0, QColor(42, 45, 52))   # Highlight bevel
        chassis_grad.setColorAt(0.5, QColor(24, 25, 29))   # Body
        chassis_grad.setColorAt(1.0, QColor(16, 17, 20))   # Shade edge

        painter.setPen(QPen(QColor(55, 58, 68), 1.2))
        painter.setBrush(QBrush(chassis_grad))
        painter.drawEllipse(QPointF(0, 0), r, r)

        # 5. Front Bumper Mechanical Seam
        painter.setPen(QPen(QColor(14, 15, 17), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(-r + 1.5, -r + 1.5, (r - 1.5) * 2, (r - 1.5) * 2), int(10 * 16), int(160 * 16))

        # Front obstacle sensor window (dark glossy acrylic slit)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(12, 13, 16)))
        painter.drawRoundedRect(QRectF(-8, -r + 1.5, 16, 2.5), 1, 1)

        # 6. Recessed Dustbin Lid Line
        painter.setPen(QPen(QColor(36, 38, 44), 1.0))
        painter.drawArc(QRectF(-r * 0.8, -r * 0.8, r * 1.6, r * 1.6), int(200 * 16), int(140 * 16))

        # 7. Side Brush (Front-right, 3-arm industrial sweep)
        self._draw_side_brush(painter, r)

        # 8. Raised LDS LiDAR Turret
        turret_r = 7.5
        # Turret drop shadow
        turret_shadow = QRadialGradient(0.5, 1.5, turret_r + 2)
        turret_shadow.setColorAt(0.0, QColor(0, 0, 0, 160))
        turret_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(turret_shadow))
        painter.drawEllipse(QPointF(0.5, 1.5), turret_r + 1.5, turret_r + 1.5)

        # Turret body (Brushed metallic ring)
        turret_grad = QLinearGradient(-turret_r, -turret_r, turret_r, turret_r)
        turret_grad.setColorAt(0.0, QColor(75, 78, 88))
        turret_grad.setColorAt(0.5, QColor(35, 37, 43))
        turret_grad.setColorAt(1.0, QColor(20, 21, 25))

        painter.setPen(QPen(QColor(85, 88, 100), 1.0))
        painter.setBrush(QBrush(turret_grad))
        painter.drawEllipse(QPointF(0, 0), turret_r, turret_r)

        # Optical aperture slot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(10, 11, 13)))
        painter.drawEllipse(QPointF(0, 0), turret_r - 2.0, turret_r - 2.0)

        # Rotating ruby laser diode
        if self.state != self.STATE_DOCK:
            sensor_x = math.cos(self.laser_sensor_rot) * 3.5
            sensor_y = math.sin(self.laser_sensor_rot) * 3.5
            painter.setBrush(QBrush(QColor(239, 68, 68)))  # Ruby red
            painter.drawEllipse(QPointF(sensor_x, sensor_y), 1.2, 1.2)

        # Turret top cap (dark satin acrylic)
        painter.setPen(QPen(QColor(50, 53, 62), 0.8))
        painter.setBrush(QBrush(QColor(26, 28, 33)))
        painter.drawEllipse(QPointF(0, 0), turret_r - 3.2, turret_r - 3.2)

        # 9. Capacitive Power / Status LED
        led_color = QColor(52, 211, 153) if self.state == self.STATE_DOCK else QColor(96, 165, 250)
        if self.state == self.STATE_STRAIN:
            led_color = QColor(239, 68, 68)
        elif self.is_grabbed:
            led_color = QColor(245, 158, 11)

        pulse = 0.8 + 0.2 * math.sin(time.time() * 4.0)
        led_color.setAlpha(int(240 * pulse))
        painter.setBrush(QBrush(led_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, -r * 0.58), 1.6, 1.6)

        painter.restore()

        # 10. Minimalist Suspension Alert Tag
        if self.is_grabbed:
            self._draw_lift_tag(painter, pos_x, pos_y - r - 18)

    def _draw_side_brush(self, painter: QPainter, r: float):
        painter.save()
        bx = r * 0.68
        by = -r * 0.68
        painter.translate(bx, by)
        painter.rotate(math.degrees(self.side_brush_angle))

        # Precision 3-arm sweep
        painter.setPen(QPen(QColor(210, 213, 222), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(3):
            arm_angle = i * (math.pi * 2 / 3)
            ax = math.cos(arm_angle) * 8.5
            ay = math.sin(arm_angle) * 8.5
            painter.drawLine(0, 0, int(ax), int(ay))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 32, 38)))
        painter.drawEllipse(QPointF(0, 0), 2.0, 2.0)
        painter.restore()

    def _draw_wheels(self, painter: QPainter, r: float):
        painter.save()
        ext = self.lift_height * 5.0
        for side in [-1, 1]:
            wx = side * (r + ext - 2)
            wy = 0.0

            # Spring strut
            painter.setPen(QPen(QColor(150, 155, 168), 1.2))
            painter.drawLine(int(side * (r - 4)), int(wy), int(wx), int(wy))

            # Rubber wheel
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
        """Minimalist, architectural control HUD (zero emoji, refined typography)."""
        painter.save()
        w = 420
        h = 38
        x = (self.screen_w - w) / 2
        y = 18

        hud_rect = QRectF(x, y, w, h)
        painter.setPen(QPen(QColor(48, 52, 62, 220), 1))
        painter.setBrush(QBrush(QColor(16, 17, 21, 235)))
        painter.drawRoundedRect(hud_rect, 19, 19)

        font_label = QFont("Segoe UI", 9, QFont.Weight.Medium)
        painter.setFont(font_label)

        if self.state == self.STATE_DOCK:
            # Active status dot
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(52, 211, 153)))  # Emerald
            painter.drawEllipse(QPointF(x + 22, y + h / 2), 3.5, 3.5)

            painter.setPen(QColor(220, 224, 234))
            painter.drawText(QRectF(x + 34, y, 180, h), Qt.AlignmentFlag.AlignVCenter, "Kuma LDS  ·  Ready at Dock")

            # Solid Start Button (Clean, high-contrast)
            start_btn = QRectF(x + w - 195, y + 5, 110, 28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(240, 242, 248)))
            painter.drawRoundedRect(start_btn, 14, 14)

            btn_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
            painter.setFont(btn_font)
            painter.setPen(QColor(15, 16, 20))
            painter.drawText(start_btn, Qt.AlignmentFlag.AlignCenter, "Clean Desktop")

            # Close Button
            close_btn = QRectF(x + w - 76, y + 5, 68, 28)
            painter.setBrush(QBrush(QColor(30, 32, 38)))
            painter.setPen(QPen(QColor(50, 54, 64), 1))
            painter.drawRoundedRect(close_btn, 14, 14)
            painter.setPen(QColor(160, 166, 180))
            painter.setFont(font_label)
            painter.drawText(close_btn, Qt.AlignmentFlag.AlignCenter, "Close")

        else:
            state_text_map = {
                self.STATE_SCAN: "Scanning desktop...",
                self.STATE_NAVIGATE: f"Cleaning · {len(self.sucked_items)} of {len(self.eligible_items)} files",
                self.STATE_VACUUM: "Vacuuming item...",
                self.STATE_STRAIN: "High-density file...",
                self.STATE_RETURNING: "Returning to dock...",
            }
            status_text = state_text_map.get(self.state, "Cleaning in progress")

            # Active pulsing dot
            pulse_color = QColor(96, 165, 250)
            if self.state == self.STATE_STRAIN:
                pulse_color = QColor(239, 68, 68)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(pulse_color))
            painter.drawEllipse(QPointF(x + 22, y + h / 2), 3.5, 3.5)

            painter.setPen(QColor(220, 224, 234))
            painter.drawText(QRectF(x + 34, y, 260, h), Qt.AlignmentFlag.AlignVCenter, f"Kuma LDS  ·  {status_text}")

            # Cancel Button
            stop_btn = QRectF(x + w - 90, y + 5, 82, 28)
            painter.setBrush(QBrush(QColor(36, 38, 46)))
            painter.setPen(QPen(QColor(60, 64, 76), 1))
            painter.drawRoundedRect(stop_btn, 14, 14)
            painter.setPen(QColor(220, 224, 234))
            painter.setFont(font_label)
            painter.drawText(stop_btn, Qt.AlignmentFlag.AlignCenter, "Cancel")

        painter.restore()
