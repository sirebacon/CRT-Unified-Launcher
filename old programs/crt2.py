import pygame
import sys

# --- TARGET CONFIGURATION ---
DISPLAY_INDEX = 1   # Targets your OSSC/CRT secondary display
SCREEN_WIDTH = 1280 
SCREEN_HEIGHT = 720
FPS = 60

def main():
    pygame.init()
    
    # Force output to the CRT monitor (Index 1)
    try:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME, display=DISPLAY_INDEX)
    except Exception as e:
        print(f"Target display {DISPLAY_INDEX} not found, falling back to primary. Error: {e}")
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 18)

    # --- STARTING WITH YOUR MEASURED DATA ---
    rect_x, rect_y = 82, 79        # Your Top-Left Offset
    rect_w, rect_h = 1024, 562    # Your Physical Viewable Area
    
    # Theoretical "Square Pixel" width for 4:3 inside your viewable window
    # Adjust this 'ideal_w' using A/D keys until the Cyan circle is perfectly round
    ideal_w = 750 

    running = True
    while running:
        screen.fill((0, 0, 0)) # The 'Overscan' Void

        # 1. Background Grid (1280x720) to check OSSC stability
        for i in range(0, SCREEN_WIDTH + 1, 64):
            pygame.draw.line(screen, (40, 40, 40), (i, 0), (i, SCREEN_HEIGHT))
        for j in range(0, SCREEN_HEIGHT + 1, 72):
            pygame.draw.line(screen, (40, 40, 40), (0, j), (SCREEN_WIDTH, j))

        # 2. Draw the Physical Viewable Boundary (Red)
        # This represents your CRT's plastic bezel edges
        viewable_rect = pygame.Rect(rect_x, rect_y, rect_w, rect_h)
        pygame.draw.rect(screen, (255, 0, 0), viewable_rect, 2)

        # 3. Draw the Corrected 4:3 Game Canvas (Green)
        # This is where RetroArch should actually render
        game_rect = pygame.Rect(rect_x + (rect_w - ideal_w)//2, rect_y, ideal_w, rect_h)
        pygame.draw.rect(screen, (0, 255, 0), game_rect, 2)

        # 4. The Geometry Check (Cyan Circle)
        # Adjust 'ideal_w' with keys until this is a perfect circle on the CRT
        center_pts = (game_rect.centerx, game_rect.centery)
        radius = rect_h // 3
        pygame.draw.circle(screen, (0, 255, 255), center_pts, radius, 2)
        pygame.draw.line(screen, (0, 150, 150), (center_pts[0], rect_y), (center_pts[0], rect_y + rect_h), 1)

        # 5. On-Screen Telemetry
        info = [
            f"OSSC SIGNAL: 720p",
            f"VIEWABLE (RED): {rect_w}x{rect_h} @ {rect_x},{rect_y}",
            f"GAME CANVAS (GREEN): {ideal_w}x{rect_h}",
            f"SQUARE PIXEL WIDTH: {ideal_w} (Adjust until Circle is round)",
            "---------------------------------",
            "Arrows: Move Viewable Box | WASD: Resize Viewable Box",
            "Q/E: Fine-tune Game Canvas Width (Green)",
            "ESC: Quit"
        ]
        for idx, line in enumerate(info):
            text = font.render(line, True, (255, 255, 255))
            screen.blit(text, (rect_x + 20, rect_y + 20 + (idx * 22)))

        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False

        # Input Handling
        keys = pygame.key.get_pressed()
        step = 5 if keys[pygame.K_LSHIFT] else 1
        
        # Adjust Physical Viewable Area (Red Box)
        if keys[pygame.K_UP]:    rect_y -= step
        if keys[pygame.K_DOWN]:  rect_y += step
        if keys[pygame.K_LEFT]:  rect_x -= step
        if keys[pygame.K_RIGHT]: rect_x += step
        if keys[pygame.K_w]:     rect_h -= step
        if keys[pygame.K_s]:     rect_h += step
        if keys[pygame.K_a]:     rect_w -= step
        if keys[pygame.K_d]:     rect_w += step
        
        # Adjust Aspect Ratio Correction (Green Box)
        if keys[pygame.K_q]:     ideal_w -= step
        if keys[pygame.K_e]:     ideal_w += step

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()