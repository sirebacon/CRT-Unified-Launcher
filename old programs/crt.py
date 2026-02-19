import pygame
import sys

# --- 720p CONFIGURATION ---
DISPLAY_INDEX = 1  
SCREEN_WIDTH = 1280 
SCREEN_HEIGHT = 720
FPS = 60

def main():
    pygame.init()
    
    try:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME, display=DISPLAY_INDEX)
    except:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 20)

    # Starting values (centered 4:3-ish box within 720p)
    rect_w, rect_h = 960, 720 
    rect_x, rect_y = (SCREEN_WIDTH - rect_w) // 2, 0

    running = True
    while running:
        screen.fill((0, 0, 0))

        # 1. Background Grid (1280x720 grid)
        for i in range(0, SCREEN_WIDTH + 1, 64):
            pygame.draw.line(screen, (30, 30, 30), (i, 0), (i, SCREEN_HEIGHT))
        for j in range(0, SCREEN_HEIGHT + 1, 72):
            pygame.draw.line(screen, (30, 30, 30), (0, j), (SCREEN_WIDTH, j))

        # 2. Draw the Usable Space Box (Green)
        cal_rect = pygame.Rect(rect_x, rect_y, rect_w, rect_h)
        pygame.draw.rect(screen, (0, 255, 0), cal_rect, 2)

        # 3. Geometry Check: The Perfect Circle
        # If this looks like an oval on your TV, your downscaler is stretching the image.
        center_pts = (rect_x + rect_w // 2, rect_y + rect_h // 2)
        radius = min(rect_w, rect_h) // 3
        pygame.draw.circle(screen, (0, 255, 255), center_pts, radius, 2) # Cyan Circle
        pygame.draw.line(screen, (200, 0, 0), (center_pts[0], rect_y), (center_pts[0], rect_y + rect_h), 1) # Center Vertical
        pygame.draw.line(screen, (200, 0, 0), (rect_x, center_pts[1]), (rect_x + rect_w, center_pts[1]), 1) # Center Horizontal

        # 4. Display Data
        info = [
            f"SIGNAL: 720p (1280x720)",
            f"USABLE: {rect_w}x{rect_h}",
            f"OFFSET: {rect_x}, {rect_y}",
            "Arrows: Move | WASD: Resize",
            "SHIFT: Fast Move | 'P': Save PNG",
            "ESC: Quit"
        ]
        for idx, line in enumerate(info):
            text = font.render(line, True, (255, 255, 255))
            screen.blit(text, (rect_x + 15, rect_y + 15 + (idx * 22)))

        # 5. Controls
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                if event.key == pygame.K_p:
                    try:
                        sub_surface = screen.subsurface(cal_rect)
                        pygame.image.save(sub_surface, "crt_720p_usable.png")
                        print(f"Captured {rect_w}x{rect_h} area.")
                    except ValueError:
                        print("Error: Box is outside screen bounds!")

        keys = pygame.key.get_pressed()
        step = 5 if keys[pygame.K_LSHIFT] else 1
        if keys[pygame.K_UP]:    rect_y -= step
        if keys[pygame.K_DOWN]:  rect_y += step
        if keys[pygame.K_LEFT]:  rect_x -= step
        if keys[pygame.K_RIGHT]: rect_x += step
        if keys[pygame.K_w]:     rect_h -= step
        if keys[pygame.K_s]:     rect_h += step
        if keys[pygame.K_a]:     rect_w -= step
        if keys[pygame.K_d]:     rect_w += step

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()