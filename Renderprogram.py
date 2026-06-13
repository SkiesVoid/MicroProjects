import math
import sys
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import pygame
from pygame.locals import DOUBLEBUF, OPENGL
from OpenGL.GL import *
from OpenGL.GLU import *


Vec3 = Tuple[float, float, float]
Face = Tuple[int, ...]


@dataclass
class Mesh:
    vertices: List[Vec3]
    faces: List[Face]


@dataclass
class SceneObject:
    name: str
    mesh: Mesh
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    color: Tuple[float, float, float] = (0.70, 0.78, 0.92)


class PrimitiveFactory:
    @staticmethod
    def cube(size: float = 1.0) -> Mesh:
        s = size / 2.0
        vertices = [
            (-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
            (-s, -s, s),  (s, -s, s),  (s, s, s),  (-s, s, s),
        ]
        faces = [
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]
        return Mesh(vertices, faces)

    @staticmethod
    def sphere(radius: float = 1.0, lat_steps: int = 18, lon_steps: int = 24) -> Mesh:
        vertices: List[Vec3] = []
        faces: List[Face] = []

        top_index = 0
        vertices.append((0.0, radius, 0.0))

        for i in range(1, lat_steps):
            phi = math.pi * i / lat_steps
            y = radius * math.cos(phi)
            ring_r = radius * math.sin(phi)
            for j in range(lon_steps):
                theta = 2.0 * math.pi * j / lon_steps
                x = ring_r * math.cos(theta)
                z = ring_r * math.sin(theta)
                vertices.append((x, y, z))

        bottom_index = len(vertices)
        vertices.append((0.0, -radius, 0.0))

        def ring_index(row: int, col: int) -> int:
            return 1 + row * lon_steps + (col % lon_steps)

        ring_rows = lat_steps - 1

        for col in range(lon_steps):
            faces.append((top_index, ring_index(0, col + 1), ring_index(0, col)))

        for row in range(ring_rows - 1):
            for col in range(lon_steps):
                faces.append((
                    ring_index(row, col),
                    ring_index(row, col + 1),
                    ring_index(row + 1, col + 1),
                    ring_index(row + 1, col),
                ))

        last_row = ring_rows - 1
        for col in range(lon_steps):
            faces.append((bottom_index, ring_index(last_row - 1, col), ring_index(last_row - 1, col + 1)))

        return Mesh(vertices, faces)

    @staticmethod
    def cylinder(radius: float = 0.7, height: float = 1.5, segments: int = 24) -> Mesh:
        h = height / 2.0
        vertices: List[Vec3] = []
        faces: List[Face] = []

        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            vertices.append((radius * math.cos(a), -h, radius * math.sin(a)))
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            vertices.append((radius * math.cos(a), h, radius * math.sin(a)))

        bottom_center = len(vertices)
        vertices.append((0.0, -h, 0.0))
        top_center = len(vertices)
        vertices.append((0.0, h, 0.0))

        for i in range(segments):
            n = (i + 1) % segments
            faces.append((i, n, segments + n, segments + i))
            faces.append((bottom_center, n, i))
            faces.append((top_center, segments + i, segments + n))

        return Mesh(vertices, faces)

    @staticmethod
    def cone(radius: float = 0.8, height: float = 1.6, segments: int = 24) -> Mesh:
        h = height / 2.0
        vertices: List[Vec3] = []
        faces: List[Face] = []

        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            vertices.append((radius * math.cos(a), -h, radius * math.sin(a)))

        tip = len(vertices)
        vertices.append((0.0, h, 0.0))
        base_center = len(vertices)
        vertices.append((0.0, -h, 0.0))

        for i in range(segments):
            n = (i + 1) % segments
            faces.append((i, n, tip))
            faces.append((base_center, i, n))

        return Mesh(vertices, faces)


def face_normal(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    mag = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / mag, ny / mag, nz / mag


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Lightweight 3D Shape Manipulator - OpenGL")
        self.width = 1400
        self.height = 900
        pygame.display.set_mode((self.width, self.height), DOUBLEBUF | OPENGL)

        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.big_font = pygame.font.SysFont("consolas", 22, bold=True)

        self.scene: List[SceneObject] = []
        self.selected_index: int = 0
        self.render_wireframe = False
        self.show_help = True

        self.camera_yaw = 35.0
        self.camera_pitch = 20.0
        self.camera_distance = 10.0
        self.camera_target = [0.0, 0.0, 0.0]

        self.dragging = False
        self.panning = False
        self.last_mouse = (0, 0)

        self.setup_opengl()
        self.add_default_scene()

    def setup_opengl(self):
        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, self.width / self.height, 0.1, 1000.0)
        glMatrixMode(GL_MODELVIEW)

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        glFrontFace(GL_CCW)

        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT0, GL_POSITION, (6.0, 8.0, 10.0, 1.0))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.95, 0.95, 0.95, 1.0))
        glLightfv(GL_LIGHT0, GL_SPECULAR, (0.5, 0.5, 0.5, 1.0))
        glLightfv(GL_LIGHT1, GL_POSITION, (-8.0, 4.0, -6.0, 1.0))
        glLightfv(GL_LIGHT1, GL_DIFFUSE, (0.3, 0.3, 0.4, 1.0))

        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, (0.2, 0.2, 0.2, 1.0))
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 24.0)

        glClearColor(0.03, 0.04, 0.06, 1.0)

    def resize_viewport(self, width: int, height: int):
        self.width = max(1, width)
        self.height = max(1, height)
        pygame.display.set_mode((self.width, self.height), DOUBLEBUF | OPENGL | pygame.RESIZABLE)
        glViewport(0, 0, self.width, self.height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, self.width / self.height, 0.1, 1000.0)
        glMatrixMode(GL_MODELVIEW)

    def make_object(self, primitive: str, name: str) -> SceneObject:
        if primitive == "cube":
            mesh = PrimitiveFactory.cube()
            color = (0.75, 0.75, 0.86)
        elif primitive == "sphere":
            mesh = PrimitiveFactory.sphere()
            color = (0.74, 0.74, 0.80)
        elif primitive == "cylinder":
            mesh = PrimitiveFactory.cylinder()
            color = (0.55, 0.82, 0.98)
        elif primitive == "cone":
            mesh = PrimitiveFactory.cone()
            color = (0.90, 0.68, 0.44)
        else:
            raise ValueError(f"Unknown primitive {primitive}")
        return SceneObject(name=name, mesh=mesh, color=color)

    def add_default_scene(self):
        head = self.make_object("sphere", "Sphere 1")
        body = self.make_object("cylinder", "Cylinder 2")
        head.position = [0.0, 1.4, 0.0]
        head.scale = [0.85, 1.0, 0.85]
        body.position = [0.0, -0.2, 0.0]
        body.scale = [1.0, 1.5, 0.6]
        self.scene = [head, body]
        self.selected_index = 0

    def add_primitive(self, primitive: str):
        obj = self.make_object(primitive, f"{primitive.title()} {len(self.scene) + 1}")
        obj.position = [len(self.scene) * 0.9, 0.0, 0.0]
        self.scene.append(obj)
        self.selected_index = len(self.scene) - 1

    def selected_object(self) -> Optional[SceneObject]:
        if not self.scene:
            return None
        self.selected_index %= len(self.scene)
        return self.scene[self.selected_index]

    def delete_selected(self):
        if not self.scene:
            return
        del self.scene[self.selected_index]
        if self.scene:
            self.selected_index %= len(self.scene)
        else:
            self.selected_index = 0

    def duplicate_selected(self):
        obj = self.selected_object()
        if obj is None:
            return
        clone = SceneObject(
            name=f"{obj.name} Copy",
            mesh=obj.mesh,
            position=[obj.position[0] + 0.8, obj.position[1], obj.position[2]],
            rotation=obj.rotation[:],
            scale=obj.scale[:],
            color=obj.color,
        )
        self.scene.append(clone)
        self.selected_index = len(self.scene) - 1

    def set_camera(self):
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        yaw = math.radians(self.camera_yaw)
        pitch = math.radians(self.camera_pitch)
        cp = math.cos(pitch)

        eye_x = self.camera_target[0] + self.camera_distance * cp * math.sin(yaw)
        eye_y = self.camera_target[1] + self.camera_distance * math.sin(pitch)
        eye_z = self.camera_target[2] + self.camera_distance * cp * math.cos(yaw)

        gluLookAt(
            eye_x, eye_y, eye_z,
            self.camera_target[0], self.camera_target[1], self.camera_target[2],
            0.0, 1.0, 0.0,
        )

    def draw_grid(self, size: int = 20, step: float = 1.0):
        glDisable(GL_LIGHTING)
        glColor3f(0.12, 0.14, 0.18)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(-size, size + 1):
            glVertex3f(-size * step, 0.0, i * step)
            glVertex3f(size * step, 0.0, i * step)
            glVertex3f(i * step, 0.0, -size * step)
            glVertex3f(i * step, 0.0, size * step)
        glEnd()
        glEnable(GL_LIGHTING)

    def draw_axes(self):
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glColor3f(1.0, 0.35, 0.35)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(2.5, 0.0, 0.0)
        glColor3f(0.35, 1.0, 0.35)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 2.5, 0.0)
        glColor3f(0.35, 0.65, 1.0)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 2.5)
        glEnd()
        glEnable(GL_LIGHTING)

    def draw_mesh_solid(self, obj: SceneObject, selected: bool):
        glPushMatrix()
        glTranslatef(*obj.position)
        glRotatef(obj.rotation[0], 1, 0, 0)
        glRotatef(obj.rotation[1], 0, 1, 0)
        glRotatef(obj.rotation[2], 0, 0, 1)
        glScalef(*obj.scale)

        color = obj.color
        if selected:
            color = tuple(min(1.0, c + 0.16) for c in color)
        glColor3f(*color)

        for face in obj.mesh.faces:
            if len(face) < 3:
                continue
            a = obj.mesh.vertices[face[0]]
            b = obj.mesh.vertices[face[1]]
            c = obj.mesh.vertices[face[2]]
            n = face_normal(a, b, c)
            mode = GL_TRIANGLES if len(face) == 3 else GL_POLYGON
            glBegin(mode)
            glNormal3f(*n)
            for idx in face:
                glVertex3f(*obj.mesh.vertices[idx])
            glEnd()

        glPopMatrix()

    def draw_mesh_wireframe(self, obj: SceneObject, selected: bool):
        glPushMatrix()
        glTranslatef(*obj.position)
        glRotatef(obj.rotation[0], 1, 0, 0)
        glRotatef(obj.rotation[1], 0, 1, 0)
        glRotatef(obj.rotation[2], 0, 0, 1)
        glScalef(*obj.scale)

        glDisable(GL_LIGHTING)
        glColor3f(0.65, 0.90, 1.00) if selected else glColor3f(0.85, 0.85, 0.88)
        glLineWidth(2.0 if selected else 1.0)
        for face in obj.mesh.faces:
            mode = GL_LINE_LOOP
            glBegin(mode)
            for idx in face:
                glVertex3f(*obj.mesh.vertices[idx])
            glEnd()
        glEnable(GL_LIGHTING)
        glPopMatrix()

    def draw_scene(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.set_camera()
        self.draw_grid()
        self.draw_axes()

        for i, obj in enumerate(self.scene):
            self.draw_mesh_solid(obj, i == self.selected_index)

        if self.render_wireframe:
            glDisable(GL_DEPTH_TEST)
            for i, obj in enumerate(self.scene):
                self.draw_mesh_wireframe(obj, i == self.selected_index)
            glEnable(GL_DEPTH_TEST)

    def draw_text(self, text: str, x: int, y: int, color=(240, 240, 240), big=False):
        font = self.big_font if big else self.font
        surf = font.render(text, True, color)
        data = pygame.image.tostring(surf, "RGBA", True)
        glWindowPos2d(x, self.height - y - surf.get_height())
        glDrawPixels(surf.get_width(), surf.get_height(), GL_RGBA, GL_UNSIGNED_BYTE, data)

    def draw_overlay(self):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.width, 0, self.height, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)

        obj = self.selected_object()
        mode = "Solid + Wireframe" if self.render_wireframe else "Solid"
        self.draw_text("Lightweight 3D Shape Manipulator - z-buffered OpenGL", 16, 14, big=True)
        self.draw_text(f"Display: {mode} | Objects: {len(self.scene)}", 16, 44)
        self.draw_text(f"Camera yaw/pitch/dist: {self.camera_yaw:.1f} / {self.camera_pitch:.1f} / {self.camera_distance:.2f}", 16, 68)
        if obj is not None:
            self.draw_text(f"Selected: {obj.name}", 16, 92, (255, 210, 120))
            self.draw_text(f"Pos {tuple(round(v, 3) for v in obj.position)}", 16, 116)
            self.draw_text(f"Rot {tuple(round(v, 3) for v in obj.rotation)}", 16, 140)
            self.draw_text(f"Scale {tuple(round(v, 3) for v in obj.scale)}", 16, 164)

        if self.show_help:
            lines = [
                "Controls:",
                "Mouse drag = orbit camera",
                "Shift + drag = pan camera target",
                "Mouse wheel = zoom",
                "Tab = next object | Backspace = delete | D = duplicate",
                "1 Cube | 2 Sphere | 3 Cylinder | 4 Cone",
                "F = toggle wireframe overlay | H = hide/show help",
                "Move: Arrow keys + PageUp/PageDown",
                "Rotate: Q/A (X), W/S (Y), E/D (Z)",
                "Scale: I/K (X), O/L (Y), P/; (Z)",
                "R = reset selected transform | C = reset camera",
                "Esc = quit",
            ]
            y = 210
            for line in lines:
                self.draw_text(line, 16, y)
                y += 24

        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)

        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def handle_keydown(self, event):
        obj = self.selected_object()

        if event.key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit(0)
        elif event.key == pygame.K_h:
            self.show_help = not self.show_help
        elif event.key == pygame.K_f:
            self.render_wireframe = not self.render_wireframe
        elif event.key == pygame.K_TAB and self.scene:
            self.selected_index = (self.selected_index + 1) % len(self.scene)
        elif event.key == pygame.K_BACKSPACE:
            self.delete_selected()
        elif event.key == pygame.K_c:
            self.camera_yaw = 35.0
            self.camera_pitch = 20.0
            self.camera_distance = 10.0
            self.camera_target = [0.0, 0.0, 0.0]
        elif event.key == pygame.K_r and obj is not None:
            obj.position = [0.0, 0.0, 0.0]
            obj.rotation = [0.0, 0.0, 0.0]
            obj.scale = [1.0, 1.0, 1.0]
        elif event.key == pygame.K_1:
            self.add_primitive("cube")
        elif event.key == pygame.K_2:
            self.add_primitive("sphere")
        elif event.key == pygame.K_3:
            self.add_primitive("cylinder")
        elif event.key == pygame.K_4:
            self.add_primitive("cone")
        elif event.key == pygame.K_d:
            self.duplicate_selected()

        if obj is None:
            return

        step = 0.1
        rot_step = 5.0
        scale_step = 0.05

        if event.key == pygame.K_LEFT:
            obj.position[0] -= step
        elif event.key == pygame.K_RIGHT:
            obj.position[0] += step
        elif event.key == pygame.K_UP:
            obj.position[2] -= step
        elif event.key == pygame.K_DOWN:
            obj.position[2] += step
        elif event.key == pygame.K_PAGEUP:
            obj.position[1] += step
        elif event.key == pygame.K_PAGEDOWN:
            obj.position[1] -= step
        elif event.key == pygame.K_q:
            obj.rotation[0] += rot_step
        elif event.key == pygame.K_a:
            obj.rotation[0] -= rot_step
        elif event.key == pygame.K_w:
            obj.rotation[1] += rot_step
        elif event.key == pygame.K_s:
            obj.rotation[1] -= rot_step
        elif event.key == pygame.K_e:
            obj.rotation[2] += rot_step
        elif event.key == pygame.K_x:
            obj.rotation[2] -= rot_step
        elif event.key == pygame.K_i:
            obj.scale[0] = max(0.05, obj.scale[0] + scale_step)
        elif event.key == pygame.K_k:
            obj.scale[0] = max(0.05, obj.scale[0] - scale_step)
        elif event.key == pygame.K_o:
            obj.scale[1] = max(0.05, obj.scale[1] + scale_step)
        elif event.key == pygame.K_l:
            obj.scale[1] = max(0.05, obj.scale[1] - scale_step)
        elif event.key == pygame.K_p:
            obj.scale[2] = max(0.05, obj.scale[2] + scale_step)
        elif event.key == pygame.K_SEMICOLON:
            obj.scale[2] = max(0.05, obj.scale[2] - scale_step)

    def handle_mouse_motion(self, event):
        if not self.dragging:
            return
        mx, my = event.pos
        lx, ly = self.last_mouse
        dx = mx - lx
        dy = my - ly
        self.last_mouse = (mx, my)

        if self.panning:
            scale = max(0.01, self.camera_distance * 0.0035)
            self.camera_target[0] -= dx * scale
            self.camera_target[1] += dy * scale
        else:
            self.camera_yaw += dx * 0.35
            self.camera_pitch += dy * 0.35
            self.camera_pitch = max(-89.0, min(89.0, self.camera_pitch))

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                elif event.type == pygame.VIDEORESIZE:
                    self.resize_viewport(event.w, event.h)
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.dragging = True
                        self.panning = bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
                        self.last_mouse = event.pos
                    elif event.button == 4:
                        self.camera_distance = max(1.0, self.camera_distance * 0.9)
                    elif event.button == 5:
                        self.camera_distance = min(300.0, self.camera_distance * 1.1)
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        self.dragging = False
                elif event.type == pygame.MOUSEMOTION:
                    self.handle_mouse_motion(event)

            self.draw_scene()
            self.draw_overlay()
            pygame.display.flip()
            self.clock.tick(60)


if __name__ == "__main__":
    App().run()
