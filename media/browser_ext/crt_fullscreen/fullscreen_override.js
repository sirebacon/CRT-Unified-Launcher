// CRT Fullscreen Override — in-browser adjustment
//
// Intercepts requestFullscreen() so the element fills the Chrome window
// (position:fixed) instead of going OS fullscreen.
//
// Controls (active when fake fullscreen is on):
//   Ctrl+Alt+A       — toggle adjust mode
//   Escape           — exit fake fullscreen
//
// In adjust mode:
//   Arrow keys       — move (x / y)
//   [ / ]            — decrease / increase width
//   - / =            — decrease / increase height
//   1–6              — step: 1  5  10  25  50  100
//   Z                — undo last change
//   Ctrl+Alt+S       — save rect to localStorage (restored on next fullscreen)
//
// Saved rect key: localStorage['crt_fs_rect'] = {x,y,w,h}
(function () {
    'use strict';

    const STORAGE_KEY = 'crt_fs_rect';
    const STEPS = [1, 5, 10, 25, 50, 100];
    let _stepIdx = 2;   // default step = 10

    let _fsElement     = null;
    let _fsOrigStyle   = null;
    let _adjustMode    = false;
    let _prevRect      = null;
    let _overlay       = null;

    // ── Rect helpers ────────────────────────────────────────────────────────

    function _loadRect() {
        try { const s = localStorage.getItem(STORAGE_KEY); return s ? JSON.parse(s) : null; }
        catch (_) { return null; }
    }

    function _saveRect(r) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(r)); } catch (_) {}
    }

    function _getComputedRect() {
        if (!_fsElement) return null;
        const cs = window.getComputedStyle(_fsElement);
        return {
            x: Math.round(parseFloat(cs.left)  || 0),
            y: Math.round(parseFloat(cs.top)   || 0),
            w: Math.round(parseFloat(cs.width) || window.innerWidth),
            h: Math.round(parseFloat(cs.height)|| window.innerHeight),
        };
    }

    function _applyRect(r) {
        if (!_fsElement) return;
        _fsElement.style.setProperty('left',   r.x + 'px', 'important');
        _fsElement.style.setProperty('top',    r.y + 'px', 'important');
        _fsElement.style.setProperty('width',  r.w + 'px', 'important');
        _fsElement.style.setProperty('height', r.h + 'px', 'important');
        _fsElement.style.removeProperty('inset');
    }

    // ── Status overlay ───────────────────────────────────────────────────────

    function _ensureOverlay() {
        if (_overlay && document.documentElement.contains(_overlay)) return _overlay;
        _overlay = document.createElement('div');
        _overlay.id = '__crt_fs_overlay__';
        Object.assign(_overlay.style, {
            position:     'fixed',
            top:          '8px',
            left:         '8px',
            zIndex:       '2147483647',
            background:   'rgba(0,0,0,0.78)',
            color:        '#0f0',
            fontFamily:   'monospace',
            fontSize:     '13px',
            padding:      '6px 10px',
            borderRadius: '4px',
            pointerEvents:'none',
            whiteSpace:   'pre',
            lineHeight:   '1.6',
        });
        document.documentElement.appendChild(_overlay);
        return _overlay;
    }

    function _renderOverlay(flash) {
        const ov = _ensureOverlay();
        ov.style.display = 'block';
        if (flash) {
            ov.textContent = flash;
            return;
        }
        const r = _getComputedRect();
        if (!r) return;
        ov.textContent =
            `[CRT ADJUST]  x=${r.x}  y=${r.y}  w=${r.w}  h=${r.h}  step=${STEPS[_stepIdx]}\n` +
            `Arrows=move  [/]=width  -/==height  1-6=step  Z=undo  Ctrl+Alt+S=save  Ctrl+Alt+A=exit`;
    }

    function _hideOverlay() {
        if (_overlay) _overlay.style.display = 'none';
    }

    // ── Fake fullscreen ──────────────────────────────────────────────────────

    function _enter(el) {
        _fsElement  = el;
        _fsOrigStyle = el.getAttribute('style') || '';

        el.style.setProperty('position',   'fixed',         'important');
        el.style.setProperty('z-index',    '2147483647',     'important');
        el.style.setProperty('object-fit', 'contain',        'important');
        el.style.setProperty('background', '#000',           'important');

        const saved = _loadRect();
        if (saved) {
            _applyRect(saved);
        } else {
            el.style.setProperty('inset',  '0',     'important');
            el.style.setProperty('width',  '100vw', 'important');
            el.style.setProperty('height', '100vh', 'important');
        }

        try {
            Object.defineProperty(document, 'fullscreenElement',
                { get: () => _fsElement, configurable: true });
            Object.defineProperty(document, 'webkitFullscreenElement',
                { get: () => _fsElement, configurable: true });
            Object.defineProperty(document, 'fullscreen',
                { get: () => !!_fsElement, configurable: true });
            Object.defineProperty(document, 'webkitIsFullScreen',
                { get: () => !!_fsElement, configurable: true });
        } catch (_) {}

        document.dispatchEvent(new Event('fullscreenchange', { bubbles: true }));
        el.dispatchEvent(new Event('fullscreenchange', { bubbles: true }));
    }

    function _exit() {
        _adjustMode = false;
        _hideOverlay();

        if (_fsElement) {
            if (_fsOrigStyle) _fsElement.setAttribute('style', _fsOrigStyle);
            else              _fsElement.removeAttribute('style');
            _fsElement = null;
        }

        try {
            Object.defineProperty(document, 'fullscreenElement',
                { get: () => null, configurable: true });
            Object.defineProperty(document, 'webkitFullscreenElement',
                { get: () => null, configurable: true });
            Object.defineProperty(document, 'fullscreen',
                { get: () => false, configurable: true });
            Object.defineProperty(document, 'webkitIsFullScreen',
                { get: () => false, configurable: true });
        } catch (_) {}

        document.dispatchEvent(new Event('fullscreenchange', { bubbles: true }));
    }

    // ── Keyboard handler ─────────────────────────────────────────────────────

    document.addEventListener('keydown', function (e) {
        const ctrl_alt = e.ctrlKey && e.altKey;

        // Ctrl+Alt+A — toggle adjust mode
        if (ctrl_alt && (e.key === 'a' || e.key === 'A')) {
            if (!_fsElement) return;
            e.preventDefault(); e.stopPropagation();
            _adjustMode = !_adjustMode;
            if (_adjustMode) _renderOverlay(); else _hideOverlay();
            return;
        }

        // Ctrl+Alt+S — save rect
        if (ctrl_alt && (e.key === 's' || e.key === 'S')) {
            if (!_fsElement) return;
            e.preventDefault(); e.stopPropagation();
            const r = _getComputedRect();
            if (r) {
                _saveRect(r);
                _renderOverlay('[CRT ADJUST]  Saved!');
                setTimeout(() => { if (_adjustMode) _renderOverlay(); else _hideOverlay(); }, 1200);
            }
            return;
        }

        // Escape — exit fake fullscreen
        if (e.key === 'Escape' && _fsElement) {
            e.preventDefault();
            _exit();
            return;
        }

        // All remaining keys only active in adjust mode
        if (!_adjustMode || !_fsElement) return;
        e.preventDefault();
        e.stopPropagation();

        const step = STEPS[_stepIdx];
        const r    = _getComputedRect();
        if (!r) return;

        switch (e.key) {
            case 'ArrowLeft':   _prevRect = {...r}; r.x -= step;              _applyRect(r); break;
            case 'ArrowRight':  _prevRect = {...r}; r.x += step;              _applyRect(r); break;
            case 'ArrowUp':     _prevRect = {...r}; r.y -= step;              _applyRect(r); break;
            case 'ArrowDown':   _prevRect = {...r}; r.y += step;              _applyRect(r); break;
            case '[':           _prevRect = {...r}; r.w = Math.max(1, r.w - step); _applyRect(r); break;
            case ']':           _prevRect = {...r}; r.w += step;              _applyRect(r); break;
            case '-':           _prevRect = {...r}; r.h = Math.max(1, r.h - step); _applyRect(r); break;
            case '=': case '+': _prevRect = {...r}; r.h += step;              _applyRect(r); break;
            case '1': case '2': case '3':
            case '4': case '5': case '6':
                _stepIdx = parseInt(e.key) - 1; break;
            case 'z': case 'Z':
                if (_prevRect) { _applyRect(_prevRect); } break;
            default: return;
        }

        _renderOverlay();
    }, true);

    // ── Intercept API ────────────────────────────────────────────────────────

    Element.prototype.requestFullscreen        = function () { _enter(this); return Promise.resolve(); };
    Element.prototype.webkitRequestFullscreen  = function () { _enter(this); return Promise.resolve(); };
    Element.prototype.webkitRequestFullScreen  = function () { _enter(this); return Promise.resolve(); };

    document.exitFullscreen        = function () { _exit(); return Promise.resolve(); };
    document.webkitExitFullscreen  = function () { _exit(); return Promise.resolve(); };

})();
