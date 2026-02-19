import pygame

# --- 960p CONFIGURATION ---
DISPLAY_INDEX = 1   
SCREEN_WIDTH = 1280 
SCREEN_HEIGHT = 960

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME, display=DISPLAY_INDEX)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Consolas", 18)

    # Use your latest successful measurements as the starting point
    rect_x, rect_y = 70, 85
    rect_h = 780
    
    running = True
    while running:
        screen.fill((0, 0, 0))

        # 1. MATHEMATICAL 4:3 CALCULATION
        # This ensures the ratio is ALWAYS 1.333 regardless of height
        rect_w = int(rect_h * (4/3))

        # 2. Draw Grid
        for i in range(0, SCREEN_WIDTH + 1, 64):
            pygame.draw.line(screen, (30, 30, 30), (i, 0), (i, SCREEN_HEIGHT))

        # 3. Draw the Canvas (Green)
        canvas_rect = pygame.Rect(rect_x, rect_y, rect_w, rect_h)
        pygame.draw.rect(screen, (0, 255, 0), canvas_rect, 2)

        # 4. Geometry Check
        center = canvas_rect.center
        pygame.draw.circle(screen, (0, 255, 255), center, rect_h // 3, 2)
        pygame.draw.line(screen, (0, 255, 255), (center[0], rect_y), (center[0], rect_y + rect_h), 1)

        # 5. Telemetry
        stats = [
            f"TARGET: 1280x960",
            f"USABLE AREA: {rect_w}x{rect_h}",
            f"OFFSET: {rect_x}, {rect_y}",
            f"RATIO: {round(rect_w/rect_h, 3)}:1",
            "",
            "ARROWS : Move Position",
            "W / S  : Adjust Height (Width follows 4:3)",
            "SHIFT  : Precision (1px)",
            "P : Save final usable space | ESC: Quit"
        ]
        for idx, line in enumerate(stats):
            text = font.render(line, True, (0, 255, 0))
            screen.blit(text, (rect_x + 15, rect_y + 15 + (idx * 20)))

        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_p:
                    pygame.image.save(screen.subsurface(canvas_rect), "crt_perfect_43.png")
                if event.key == pygame.K_ESCAPE: running = False

        keys = pygame.key.get_pressed()
        step = 1 if keys[pygame.K_LSHIFT] else 5
        
        if keys[pygame.K_UP]:    rect_y -= step
        if keys[pygame.K_DOWN]:  rect_y += step
        if keys[pygame.K_LEFT]:  rect_x -= step
        if keys[pygame.K_RIGHT]: rect_x += step
        if keys[pygame.K_w]:     rect_h += step
        if keys[pygame.K_s]:     rect_h -= step

        pygame.display.flip()
        clock.tick(60)
    pygame.quit()

if __name__ == "__main__":
    main()