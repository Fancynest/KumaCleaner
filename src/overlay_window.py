import math
import os
import random
import time
from typing import Optional

from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
    QLinearGradient, QRadialGradient, QPolygonF, QPixmap
)

from desktop_scanner import DesktopItem
from sound_fx import sound_fx
import win32_helper


class Particle:
    def __init__(self, x: float, y: float, target_x: float, target_y: float):
        self.x = x
        self.y = y
        self.target_x = target_x
        self.target_y = target_y
        self.life = 1.0  # 1.0 -> 0.0
        self.decay = random.uniform(0.03, 0.06)
        self.size = random.uniform(2.0, 5.0)
        # Random initial outward swirl
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(1.5, 4.5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.color = random.choice([
            QColor(255, 215, 0, 220),    # gold dust
            QColor(135, 206, 250, 220),  # cyan spark
            QColor(255, 255, 255, 240),  # bright fleck
            QColor(180, 180, 200, 200),  # micro dust
        ])

    def update(self):
        # Steer toward target with swirl
        dx = self.target_x - self.x
        dy = self.target_y - self.y
        dist = math.hypot(dx, dy) + 0.1
        ax = (dx / dist) * 4.5
        ay = (dy / dist) * 4.5
        self.vx = self.vx * 0.88 + ax * 0.18
        self.vy = self.vy * 0.88 + ay * 0.18
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

        # Window settings
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

        # Load Realistic Assets
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        self.robot_pixmap = QPixmap(os.path.join(assets_dir, "robot_vacuum.png"))
        self.dock_pixmap = QPixmap(os.path.join(assets_dir, "dock_station.png"))

        # Dimensions & Sizing
        self.vacuum_radius = 44.0  # 88px diameter
        self.vacuum_diameter = self.vacuum_radius * 2

        # Dock station sizing (approx 95px wide, 145px tall)
        self.dock_w = 96
        self.dock_h = 146
        self.dock_x = self.screen_w - 150
        self.dock_y = self.screen_h - 180

        # Vacuum position starts directly on dock
        self.kuma_x = float(self.dock_x)
        self.kuma_y = float(self.dock_y + 25)
        self.kuma_angle = -math.pi * 0.5  # Facing UP (north) away from dock

        self.state = self.STATE_DOCK
        self.state_time = 0.0

        # Grab / Drag interaction
        self.is_grabbed = False
        self.grab_offset_x = 0.0
        self.grab_offset_y = 0.0
        self.lift_height = 0.0  # 0.0 to 1.0 for suspension animation
        self.wheel_spin_angle = 0.0

        # LiDAR scanning variables
        self.lidar_angle = 0.0
        self.lidar_radius = 50.0
        self.lidar_max_radius = math.hypot(self.screen_w, self.screen_h) * 0.6
        self.locked_items: set[int] = set()

        # Target and path
        self.current_target_index: Optional[int] = None
        self.suction_progress = 0.0
        self.strain_timer = 0.0
        self.shake_offset = QPointF(0, 0)

        # Dynamic animation elements
        self.side_brush_angle = 0.0
        self.laser_sensor_rot = 0.0
        self.particles: list[Particle] = []

        # Sort eligible items by traveling-salesperson/nearest neighbor
        self._plan_cleaning_route()

        # 60 FPS Animation Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.game_loop)
        self.last_tick = time.time()

        # Hide real desktop icons when overlay activates
        win32_helper.set_desktop_icons_visible(False)

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
        self.state = self.STATE_SCAN
        self.state_time = 0.0
        sound_fx.play('ping')

    def closeEvent(self, event):
        win32_helper.set_desktop_icons_visible(True)
        self.timer.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            win32_helper.set_desktop_icons_visible(True)
            self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            dist = math.hypot(pos.x() - self.kuma_x, pos.y() - self.kuma_y)
            if dist <= self.vacuum_radius + 18:
                self.is_grabbed = True
                self.grab_offset_x = self.kuma_x - pos.x()
                self.grab_offset_y = self.kuma_y - pos.y()
                sound_fx.play('squeak')
                self.update()
                return

            # HUD Stop button
            hud_rect = QRectF(self.screen_w / 2 - 220, 20, 440, 48)
            if hud_rect.contains(pos):
                stop_btn_rect = QRectF(self.screen_w / 2 + 100, 28, 106, 32)
                if stop_btn_rect.contains(pos):
                    win32_helper.set_desktop_icons_visible(True)
                    self.close()

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

        # Animate side brush and internal laser turret
        brush_speed = 18.0 if self.state == self.STATE_VACUUM else 10.0
        self.side_brush_angle += dt * brush_speed
        self.laser_sensor_rot += dt * 14.0

        # Animate lift height for suspension
        target_lift = 1.0 if self.is_grabbed else 0.0
        self.lift_height += (target_lift - self.lift_height) * min(1.0, dt * 12.0)
        if self.is_grabbed:
            self.wheel_spin_angle += dt * 25.0

        # Particle physics
        self.particles = [p for p in self.particles if p.update()]

        if self.is_grabbed:
            self.update()
            return

        # State Machine
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
        self.lidar_angle += dt * 6.5
        self.lidar_radius += dt * 480.0

        for idx, item in enumerate(self.eligible_items):
            if idx not in self.locked_items:
                dist = math.hypot(item.x + 24 - self.kuma_x, item.y + 24 - self.kuma_y)
                if dist <= self.lidar_radius:
                    self.locked_items.add(idx)
                    sound_fx.play('ping')

        if self.lidar_radius >= self.lidar_max_radius or self.state_time > 3.0:
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
        self.kuma_angle += diff * min(1.0, dt * 9.0)

        speed = 280.0 * dt
        if dist > 24:
            self.kuma_x += math.cos(self.kuma_angle) * min(dist, speed)
            self.kuma_y += math.sin(self.kuma_angle) * min(dist, speed)
        else:
            self.state = self.STATE_VACUUM
            self.suction_progress = 0.0

    def _update_vacuum(self, dt: float):
        target = self.eligible_items[self.current_target_index]
        tx = target.x + 24
        ty = target.y + 24

        mouth_x = self.kuma_x + math.cos(self.kuma_angle) * (self.vacuum_radius - 8)
        mouth_y = self.kuma_y + math.sin(self.kuma_angle) * (self.vacuum_radius - 8)

        # Suction dust swirl particles
        for _ in range(4):
            self.particles.append(Particle(
                tx + random.uniform(-22, 22),
                ty + random.uniform(-22, 22),
                mouth_x,
                mouth_y
            ))

        self.suction_progress += dt * 2.4

        if self.suction_progress >= 1.0:
            sound_fx.play('pop')
            self.sucked_items.append(target)

            if target.is_heavy:
                self.state = self.STATE_STRAIN
                self.strain_timer = 1.6
                sound_fx.play('strain')
            else:
                self._next_target()

    def _update_strain(self, dt: float):
        self.strain_timer -= dt
        # High-frequency engine vibration
        self.shake_offset = QPointF(
            random.uniform(-4.5, 4.5),
            random.uniform(-4.5, 4.5)
        )
        # Rear exhaust micro-puffs
        rear_x = self.kuma_x - math.cos(self.kuma_angle) * self.vacuum_radius
        rear_y = self.kuma_y - math.sin(self.kuma_angle) * self.vacuum_radius
        for _ in range(2):
            self.particles.append(Particle(
                rear_x, rear_y,
                rear_x - math.cos(self.kuma_angle) * 35 + random.uniform(-12, 12),
                rear_y - math.sin(self.kuma_angle) * 35 + random.uniform(-12, 12)
            ))

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
        target_dock_y = self.dock_y + 25

        dx = target_dock_x - self.kuma_x
        dy = target_dock_y - self.kuma_y
        dist = math.hypot(dx, dy)

        # Approach dock facing upwards (north)
        desired_angle = math.atan2(dy, dx)
        diff = (desired_angle - self.kuma_angle + math.pi) % (2 * math.pi) - math.pi
        self.kuma_angle += diff * min(1.0, dt * 7.5)

        speed = 320.0 * dt
        if dist > 14:
            self.kuma_x += math.cos(self.kuma_angle) * min(dist, speed)
            self.kuma_y += math.sin(self.kuma_angle) * min(dist, speed)
        else:
            # Successfully docked!
            self.kuma_angle = -math.pi * 0.5
            self.timer.stop()
            self.finished_cleaning.emit(self.sucked_items)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Draw Charging Dock Station
        self._draw_dock(painter)

        # 2. Draw Desktop Icons (with suction warp)
        self._draw_desktop_icons(painter)

        # 3. Draw LiDAR Sweep
        if self.state == self.STATE_SCAN:
            self._draw_lidar(painter)

        # 4. Draw Particles (dust swirls)
        self._draw_particles(painter)

        # 5. Draw Robot Vacuum
        self._draw_vacuum(painter)

        # 6. Draw Top HUD Bar
        self._draw_hud(painter)

    def _draw_dock(self, painter: QPainter):
        painter.save()
        painter.translate(self.dock_x, self.dock_y)

        # Realistic Dock Ground Shadow
        dock_shadow = QRadialGradient(0, 15, 95)
        dock_shadow.setColorAt(0.0, QColor(0, 0, 0, 140))
        dock_shadow.setColorAt(0.5, QColor(0, 0, 0, 80))
        dock_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dock_shadow))
        painter.drawEllipse(QRectF(-self.dock_w * 0.7, -self.dock_h * 0.5, self.dock_w * 1.4, self.dock_h * 1.2))

        # Render Dock Station Sprite
        if not self.dock_pixmap.isNull():
            target_rect = QRectF(-self.dock_w / 2, -self.dock_h / 2, self.dock_w, self.dock_h)
            painter.drawPixmap(target_rect.toRect(), self.dock_pixmap)
        else:
            # Fallback procedural dock
            painter.setPen(QPen(QColor(60, 60, 75), 2))
            painter.setBrush(QBrush(QColor(30, 30, 38)))
            painter.drawRoundedRect(int(-self.dock_w / 2), int(-self.dock_h / 2), self.dock_w, self.dock_h, 12, 12)

        # Dynamic Dock Status LED Indicator Bar
        led_color = QColor(166, 227, 161) if self.state == self.STATE_DOCK else QColor(137, 180, 250)
        pulse = 0.7 + 0.3 * math.sin(time.time() * 4.0)
        led_color.setAlpha(int(255 * pulse))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(led_color))
        painter.drawRoundedRect(QRectF(-14, -self.dock_h / 2 + 12, 28, 4), 2, 2)

        # Dock Glow light
        glow = QRadialGradient(0, -self.dock_h / 2 + 14, 18)
        glow.setColorAt(0.0, QColor(led_color.red(), led_color.green(), led_color.blue(), 100))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(0, -self.dock_h / 2 + 14), 18, 12)

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
            scale = 1.0

            painter.save()

            if is_current_target:
                p = self.suction_progress
                mouth_x = self.kuma_x + math.cos(self.kuma_angle) * (self.vacuum_radius - 8)
                mouth_y = self.kuma_y + math.sin(self.kuma_angle) * (self.vacuum_radius - 8)

                ix = ix * (1.0 - p) + mouth_x * p
                iy = iy * (1.0 - p) + mouth_y * p
                scale = max(0.01, 1.0 - (p ** 1.5))

                painter.translate(ix + 24, iy + 24)
                painter.rotate(p * 240.0)
                painter.scale(scale, scale)
                painter.translate(-(ix + 24), -(iy + 24))

            # Futuristic targeting reticle
            if item.is_eligible and idx in self.locked_items and not is_current_target:
                reticle_color = QColor(137, 180, 250, 180)
                painter.setPen(QPen(reticle_color, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)

                # Corner brackets
                cx, cy = ix + 24, iy + 24
                sz = 26
                # Top-left
                painter.drawLine(int(cx - sz), int(cy - sz), int(cx - sz + 8), int(cy - sz))
                painter.drawLine(int(cx - sz), int(cy - sz), int(cx - sz), int(cy - sz + 8))
                # Top-right
                painter.drawLine(int(cx + sz), int(cy - sz), int(cx + sz - 8), int(cy - sz))
                painter.drawLine(int(cx + sz), int(cy - sz), int(cx + sz), int(cy - sz + 8))
                # Bottom-left
                painter.drawLine(int(cx - sz), int(cy + sz), int(cx - sz + 8), int(cy + sz))
                painter.drawLine(int(cx - sz), int(cy + sz), int(cx - sz), int(cy + sz - 8))
                # Bottom-right
                painter.drawLine(int(cx + sz), int(cy + sz), int(cx + sz - 8), int(cy + sz))
                painter.drawLine(int(cx + sz), int(cy + sz), int(cx + sz), int(cy + sz - 8))

            # Draw icon
            if item.pixmap:
                painter.drawPixmap(int(ix), int(iy), item.pixmap)
            else:
                painter.setBrush(QBrush(QColor(137, 180, 250, 180)))
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawRoundedRect(int(ix + 4), int(iy + 4), 40, 40, 6, 6)

            # Draw filename label
            if not is_current_target:
                font = QFont("Segoe UI", 9)
                painter.setFont(font)

                display_text = item.name
                if len(display_text) > 16:
                    display_text = display_text[:14] + ".."

                text_rect = QRectF(ix - 15, iy + 50, 78, 22)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(17, 17, 27, 200)))
                painter.drawRoundedRect(text_rect, 4, 4)

                painter.setPen(QColor(245, 245, 245))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, display_text)

                # Heavy file badge
                if item.is_heavy:
                    badge_rect = QRectF(ix + 30, iy - 4, 18, 18)
                    painter.setBrush(QBrush(QColor(243, 139, 168)))
                    painter.drawEllipse(badge_rect)
                    painter.setPen(QColor(17, 17, 27))
                    painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "!")

            painter.restore()

    def _draw_lidar(self, painter: QPainter):
        painter.save()
        # Expanding glowing radar ring
        pen = QPen(QColor(137, 180, 250, 160), 2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(self.kuma_x, self.kuma_y), self.lidar_radius, self.lidar_radius)

        if self.lidar_radius > 70:
            painter.setPen(QPen(QColor(166, 227, 161, 90), 1.5))
            painter.drawEllipse(QPointF(self.kuma_x, self.kuma_y), self.lidar_radius * 0.65, self.lidar_radius * 0.65)

        # Rotating laser cone
        cone_grad = QRadialGradient(self.kuma_x, self.kuma_y, self.lidar_radius)
        cone_grad.setColorAt(0.0, QColor(137, 180, 250, 160))
        cone_grad.setColorAt(1.0, QColor(137, 180, 250, 0))

        painter.setBrush(QBrush(cone_grad))
        painter.setPen(Qt.PenStyle.NoPen)

        span = 28.0
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
            color = QColor(p.color)
            color.setAlpha(int(255 * p.life))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(QPointF(p.x, p.y), p.size * p.life, p.size * p.life)
        painter.restore()

    def _draw_vacuum(self, painter: QPainter):
        painter.save()

        pos_x = self.kuma_x + self.shake_offset.x()
        pos_y = self.kuma_y + self.shake_offset.y()
        r = self.vacuum_radius

        # 1. Realistic Multi-layered Ground Shadow (Direction-aware)
        shadow_offset_y = 6.0 + self.lift_height * 24.0
        shadow_scale = 1.0 + self.lift_height * 0.35
        shadow_alpha = int(140 * (1.0 - self.lift_height * 0.45))

        shadow_grad = QRadialGradient(pos_x, pos_y + shadow_offset_y, (r + 10) * shadow_scale)
        shadow_grad.setColorAt(0.0, QColor(0, 0, 0, shadow_alpha))
        shadow_grad.setColorAt(0.6, QColor(0, 0, 0, int(shadow_alpha * 0.4)))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(shadow_grad))
        painter.drawEllipse(
            QPointF(pos_x, pos_y + shadow_offset_y),
            (r + 8) * shadow_scale,
            (r + 5) * shadow_scale
        )

        # 2. Forward 3D Obstacle Avoidance Structured Light (High-tech Laser Lines)
        if not self.is_grabbed:
            self._draw_front_lasers(painter, pos_x, pos_y)

        # 3. Transform to Robot Local Coordinates
        painter.translate(pos_x, pos_y)
        painter.rotate(math.degrees(self.kuma_angle) + 90)  # +90 aligns front bumper to top

        # 4. Animated Side Brush (Protrudes at Front-Right ~40 deg)
        self._draw_side_brush(painter, r)

        # 5. Suspended Spring Wheels (When Picked Up / Lifted)
        if self.lift_height > 0.05:
            self._draw_suspended_wheels(painter, r)

        # 6. Render High-Res Realistic Robot Vacuum Sprite
        if not self.robot_pixmap.isNull():
            target_rect = QRectF(-r, -r, r * 2, r * 2)
            painter.drawPixmap(target_rect.toRect(), self.robot_pixmap)
        else:
            # Fallback procedural body
            body_grad = QLinearGradient(-r, -r, r, r)
            body_grad.setColorAt(0.0, QColor(40, 42, 54))
            body_grad.setColorAt(1.0, QColor(20, 20, 28))
            painter.setPen(QPen(QColor(80, 85, 105), 2.5))
            painter.setBrush(QBrush(body_grad))
            painter.drawEllipse(QPointF(0, 0), r, r)

        # 7. Dynamic LiDAR Turret Laser Eye (Glows and spins)
        self._draw_lidar_turret_eye(painter)

        # 8. Front Status Light Strip
        self._draw_status_light(painter, r)

        painter.restore()

        # 9. Suspension Hazard Alert when Grabbed
        if self.is_grabbed:
            self._draw_lift_alert(painter, pos_x, pos_y - r - 28)

    def _draw_front_lasers(self, painter: QPainter, x: float, y: float):
        """Draw dual 3D structured light cross-laser scan lines on the floor."""
        painter.save()
        angle = self.kuma_angle
        dist = 55.0

        # Laser beam endpoints
        lx = x + math.cos(angle) * dist
        ly = y + math.sin(angle) * dist

        laser_color = QColor(137, 180, 250, 160)
        if self.state == self.STATE_VACUUM:
            laser_color = QColor(249, 226, 175, 190)
        elif self.state == self.STATE_STRAIN:
            laser_color = QColor(243, 139, 168, 220)

        # Draw scanning crosshair line
        spread = 28.0
        perp_angle = angle + math.pi / 2
        p1_x = lx + math.cos(perp_angle) * spread
        p1_y = ly + math.sin(perp_angle) * spread
        p2_x = lx - math.cos(perp_angle) * spread
        p2_y = ly - math.sin(perp_angle) * spread

        pen = QPen(laser_color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(p1_x, p1_y), QPointF(p2_x, p2_y))

        # Thin projection rays from bumper
        bumper_x = x + math.cos(angle) * (self.vacuum_radius - 2)
        bumper_y = y + math.sin(angle) * (self.vacuum_radius - 2)
        ray_pen = QPen(QColor(laser_color.red(), laser_color.green(), laser_color.blue(), 50), 1.0)
        painter.setPen(ray_pen)
        painter.drawLine(QPointF(bumper_x, bumper_y), QPointF(p1_x, p1_y))
        painter.drawLine(QPointF(bumper_x, bumper_y), QPointF(p2_x, p2_y))

        painter.restore()

    def _draw_side_brush(self, painter: QPainter, r: float):
        """Draw realistic spinning 3-arm bristle side-brush at front-right."""
        painter.save()
        # Front right corner position
        bx = r * 0.68
        by = -r * 0.68
        painter.translate(bx, by)
        painter.rotate(math.degrees(self.side_brush_angle))

        # 3 Bristle arms
        painter.setPen(QPen(QColor(220, 220, 230), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(3):
            arm_angle = i * (math.pi * 2 / 3)
            ax = math.cos(arm_angle) * 16.0
            ay = math.sin(arm_angle) * 16.0
            painter.drawLine(0, 0, int(ax), int(ay))
            # Bristle brush tip
            painter.setBrush(QBrush(QColor(180, 180, 195)))
            painter.drawEllipse(QPointF(ax, ay), 2.5, 2.5)

        # Center brush hub
        painter.setPen(QPen(QColor(40, 40, 50), 1))
        painter.setBrush(QBrush(QColor(20, 20, 25)))
        painter.drawEllipse(QPointF(0, 0), 4, 4)

        painter.restore()

    def _draw_suspended_wheels(self, painter: QPainter, r: float):
        """Draw extended suspension wheels on left and right when vacuum is lifted."""
        painter.save()
        extension = self.lift_height * 10.0

        for side in [-1, 1]:  # Left and right wheels
            wx = side * (r + extension - 4)
            wy = 2.0

            # Spring strut
            painter.setPen(QPen(QColor(180, 180, 190), 2))
            painter.drawLine(int(side * (r - 6)), int(wy), int(wx), int(wy))

            # Rugged Rubber Wheel
            painter.save()
            painter.translate(wx, wy)
            painter.rotate(math.degrees(self.wheel_spin_angle))

            painter.setPen(QPen(QColor(20, 20, 25), 1.5))
            painter.setBrush(QBrush(QColor(45, 45, 55)))
            painter.drawRoundedRect(-5, -12, 10, 24, 3, 3)

            # Wheel tread lines
            painter.setPen(QPen(QColor(80, 80, 95), 1.5))
            painter.drawLine(-4, -6, 4, -6)
            painter.drawLine(-4, 0, 4, 0)
            painter.drawLine(-4, 6, 4, 6)

            painter.restore()

        painter.restore()

    def _draw_lidar_turret_eye(self, painter: QPainter):
        """Draw realistic rotating laser sensor diode inside the LDS turret."""
        painter.save()
        # Rotating laser diode slit
        sensor_x = math.cos(self.laser_sensor_rot) * 9.0
        sensor_y = math.sin(self.laser_sensor_rot) * 9.0

        # Ruby laser diode dot
        laser_dot_color = QColor(255, 60, 60, 240)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(laser_dot_color))
        painter.drawEllipse(QPointF(sensor_x, sensor_y), 3.0, 3.0)

        # Micro lens glint
        glint = QRadialGradient(sensor_x, sensor_y, 8)
        glint.setColorAt(0.0, QColor(255, 100, 100, 160))
        glint.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glint))
        painter.drawEllipse(QPointF(sensor_x, sensor_y), 8, 8)

        painter.restore()

    def _draw_status_light(self, painter: QPainter, r: float):
        """Draw sleek status LED breathing strip on the front bumper."""
        painter.save()
        color = QColor(137, 180, 250)
        if self.is_grabbed:
            color = QColor(243, 139, 168)  # Alert Pink/Red
        elif self.state == self.STATE_VACUUM:
            color = QColor(249, 226, 175)  # Amber
        elif self.state == self.STATE_STRAIN:
            color = QColor(255, 75, 75)    # Danger Red
        elif self.state == self.STATE_DOCK:
            color = QColor(166, 227, 161)  # Emerald Green

        pulse = 0.75 + 0.25 * math.sin(time.time() * 6.0)
        color.setAlpha(int(240 * pulse))

        painter.setPen(QPen(color, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Front bumper arc
        painter.drawArc(QRectF(-r + 6, -r + 6, (r - 6) * 2, (r - 6) * 2), int(55 * 16), int(70 * 16))
        painter.restore()

    def _draw_lift_alert(self, painter: QPainter, x: float, y: float):
        """HUD warning bubble when vacuum is picked up."""
        painter.save()
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)

        bubble_rect = QRectF(x - 140, y - 32, 280, 32)
        painter.setPen(QPen(QColor(243, 139, 168), 1.8))
        painter.setBrush(QBrush(QColor(24, 24, 37, 235)))
        painter.drawRoundedRect(bubble_rect, 8, 8)

        painter.setPen(QColor(243, 139, 168))
        painter.drawText(bubble_rect, Qt.AlignmentFlag.AlignCenter, "⚠️ RODA TERANGKAT - SENSOR TERPICU")
        painter.restore()

    def _draw_hud(self, painter: QPainter):
        painter.save()
        w = 460
        h = 44
        x = (self.screen_w - w) / 2
        y = 24

        hud_rect = QRectF(x, y, w, h)
        painter.setPen(QPen(QColor(88, 91, 112, 160), 1.5))
        painter.setBrush(QBrush(QColor(24, 24, 37, 230)))
        painter.drawRoundedRect(hud_rect, 22, 22)

        state_labels = {
            self.STATE_SCAN: "📡 LiDAR Mapping Desktop...",
            self.STATE_NAVIGATE: f"🧹 Membersihkan ({len(self.sucked_items)}/{len(self.eligible_items)})",
            self.STATE_VACUUM: "💨 Menyedot file...",
            self.STATE_STRAIN: "💦 File berat! Motor bekerja ekstra...",
            self.STATE_RETURNING: "🏠 Menuju Docking Station...",
            self.STATE_DOCK: "⚡ Terparkir di Docking Station"
        }
        status_str = state_labels.get(self.state, "KumaCleaner LDS")

        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor(249, 226, 175))
        painter.drawText(QRectF(x + 20, y, 240, h), Qt.AlignmentFlag.AlignVCenter, f"🤖 {status_str}")

        # Stop button
        stop_btn_rect = QRectF(x + w - 120, y + 6, 106, 32)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(243, 139, 168, 210)))
        painter.drawRoundedRect(stop_btn_rect, 16, 16)

        painter.setPen(QColor(17, 17, 27))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.drawText(stop_btn_rect, Qt.AlignmentFlag.AlignCenter, "Batal (ESC)")

        painter.restore()
