import pygame
import math

# Constants
WINDOW_SIZE = 800
HEX_RADIUS = 40
GRID_ORIGIN = (WINDOW_SIZE // 2, WINDOW_SIZE // 2)

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

# Initialize Pygame
pygame.init()
screen = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE))
pygame.display.set_caption("Hexagonal Grid")

# Calculate hexagon points
def hex_corner(center, size, i):
    angle_deg = 60 * i - 30
    angle_rad = math.radians(angle_deg)
    return (center[0] + size * math.cos(angle_rad),
            center[1] + size * math.sin(angle_rad))

def draw_hexagon(surface, color, center, size):
    points = [hex_corner(center, size, i) for i in range(6)]
    pygame.draw.polygon(surface, color, points, 1)

# Function to draw hexagonal grid
def draw_hex_grid(surface, radius, window_size):
    width = radius * 3 ** 0.5
    height = radius * 1.5
    rows = int(window_size // height) + 1
    cols = int(window_size // width) + 1

    for row in range(rows):
        for col in range(cols):
            x = col * width
            y = row * height
            if row % 2 == 1:
                x += width / 2
            draw_hexagon(surface, BLACK, (x, y), radius)

# Main loop
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                running = False

    screen.fill(WHITE)
    draw_hex_grid(screen, HEX_RADIUS, WINDOW_SIZE)
    pygame.display.flip()

pygame.quit()
