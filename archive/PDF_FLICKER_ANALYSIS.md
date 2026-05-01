# PDF Preview Flickering - Root Cause Analysis

## Issues Identified

### 1. **Pixel Ratio Calculation with Empty Dependencies** (High Priority)
**Location**: [PdfViewer.jsx](uv_intelligent_demo/webapp/frontend/src/components/PdfViewer.jsx#L24-L27)

```javascript
const pixelRatio = useMemo(() => {
  if (typeof window === "undefined") return 2;
  return Math.min(3, Math.max(window.devicePixelRatio || 1, 1.6));
}, []); // ❌ Empty dependency array - PROBLEM!
```

**Problem**: The `pixelRatio` is calculated once at mount and never updates, even if:
- The window's devicePixelRatio changes (e.g., during zoom or on high-DPI displays)
- The component is re-rendered with different props

**Impact**: When the `pixelRatio` doesn't match what's needed for re-rendering, the PDF.js library might need to re-render the canvas at a different resolution, causing flickering.

**Fix**: Add explicit dependency tracking or make it dynamic:
```javascript
const pixelRatio = useMemo(() => {
  if (typeof window === "undefined") return 2;
  return Math.min(3, Math.max(window.devicePixelRatio || 1, 1.6));
}, [pageNumber, pageWidth]); // Include relevant dependencies
```

---

### 2. **Canvas Re-rendering on Every Width/Zoom Change** (Medium Priority)
**Location**: [PdfViewer.jsx](uv_intelligent_demo/webapp/frontend/src/components/PdfViewer.jsx#L16-L21)

```javascript
const pageWidth = useMemo(
  () => Math.max(Math.round(containerWidth * zoom), 320),
  [containerWidth, zoom]
);
```

**Problem**: The `pageWidth` dependency triggers re-renders whenever:
- User changes zoom level
- Window is resized
- Container's client width changes

Each change causes the `<Page>` component to recalculate and re-render the entire canvas.

**Impact**: Rapid dimension changes = rapid canvas redraws = visible flickering during interactions.

---

### 3. **ResizeObserver Firing During Load** (Medium Priority)
**Location**: [PdfViewer.jsx](uv_intelligent_demo/webapp/frontend/src/components/PdfViewer.jsx#L29-L40)

```javascript
useEffect(() => {
  function updateWidth() {
    if (containerRef.current) {
      setContainerWidth(Math.max(containerRef.current.clientWidth - 40, 320));
    }
  }
  
  updateWidth();
  const resizeObserver = new ResizeObserver(updateWidth);
  if (containerRef.current) {
    resizeObserver.observe(containerRef.current);
  }
  // ...
});
```

**Problem**: 
- The ResizeObserver fires immediately on mount
- It may also fire multiple times as the PDF document loads and renders
- Each fire triggers `setContainerWidth`, which updates `pageWidth`, which re-renders the canvas

**Impact**: During PDF load, the container might be resizing, causing cascading re-renders and flickering.

---

### 4. **Selection Change Triggers Full Re-render** (Medium Priority)
**Location**: [PdfViewer.jsx](uv_intelligent_demo/webapp/frontend/src/components/PdfViewer.jsx#L69-L78)

```javascript
useEffect(() => {
  function handleSelectionChange() {
    requestAnimationFrame(emitSelection); // ❌ Still fires on every selection
  }
  
  document.addEventListener("selectionchange", handleSelectionChange);
  return () => {
    document.removeEventListener("selectionchange", handleSelectionChange);
  };
}, [onSelectionChange]); // Recreated on every parent re-render
```

**Problem**:
- Text selection in PDF triggers `selectionchange` events
- Each selection fires `onSelectionChange` in the parent (ReportPanel)
- Parent state update (`setSelectedPreviewText`) causes PdfViewer to re-render
- Re-render might reset or re-paint the canvas

**Impact**: Selecting text causes flickering as the PDF canvas re-renders in response to parent state updates.

---

### 5. **Page Component Not Memoized** (Medium Priority)
**Location**: [PdfViewer.jsx](uv_intelligent_demo/webapp/frontend/src/components/PdfViewer.jsx#L137-L147)

```javascript
<Page
  pageNumber={pageNumber}
  width={pageWidth}
  devicePixelRatio={pixelRatio}
  renderMode="canvas"
  renderAnnotationLayer={false}
  renderTextLayer
/>
```

**Problem**: The `<Page>` component is re-created on every render. Even though `pageWidth` is memoized, the component itself is not wrapped in `React.memo()`.

**Impact**: Unnecessary re-renders of the canvas element, especially when parent component re-renders.

---

### 6. **Text Layer Overlay Conflict** (Low Priority)
**Location**: [PdfViewer.jsx](uv_intelligent_demo/webapp/frontend/src/components/PdfViewer.jsx#L141) and CSS

```javascript
renderMode="canvas"
renderTextLayer  // Renders both canvas AND text overlay
```

**Problem**: When both `renderMode="canvas"` and `renderTextLayer` are enabled:
- The canvas is rendered
- A separate text layer overlay is rendered on top
- These two layers might update at different times, causing temporary visual misalignment

**Impact**: Slight flickering or layer shift when text layer updates after canvas finishes rendering.

---

### 7. **Container Width Calculation Margin** (Low Priority)
**Location**: [PdfViewer.jsx](uv_intelligent_demo/webapp/frontend/src/components/PdfViewer.jsx#L32)

```javascript
setContainerWidth(Math.max(containerRef.current.clientWidth - 40, 320));
```

**Problem**: Subtracting 40px for padding might cause width oscillation:
- If container width is close to the padding amount
- Small variations can cause `pageWidth` to jump between values

---

## Recommended Fixes (Priority Order)

### Fix 1: Update pixelRatio dependency (CRITICAL)
```javascript
const pixelRatio = useMemo(() => {
  if (typeof window === "undefined") return 2;
  return Math.min(3, Math.max(window.devicePixelRatio || 1, 1.6));
}, [pageNumber, containerWidth]); // Add dependencies
```

### Fix 2: Debounce ResizeObserver updates (HIGH)
```javascript
useEffect(() => {
  let timeoutId;
  
  function updateWidth() {
    if (containerRef.current) {
      setContainerWidth(Math.max(containerRef.current.clientWidth - 40, 320));
    }
  }
  
  function debouncedUpdateWidth() {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(updateWidth, 100); // Debounce
  }
  
  const resizeObserver = new ResizeObserver(debouncedUpdateWidth);
  if (containerRef.current) {
    resizeObserver.observe(containerRef.current);
  }
  
  // ... rest of cleanup
});
```

### Fix 3: Memoize the Page component (MEDIUM)
```javascript
const MemoizedPage = React.memo(Page);

// Then use:
<MemoizedPage
  key={`${pageNumber}-${pageWidth}`}
  pageNumber={pageNumber}
  width={pageWidth}
  devicePixelRatio={pixelRatio}
  renderMode="canvas"
  renderAnnotationLayer={false}
  renderTextLayer
/>
```

### Fix 4: Separate text selection from PDF state (MEDIUM)
Move the selection callback to a separate effect or use a ref to avoid triggering parent re-renders that cause canvas updates.

### Fix 5: Use render mode without text layer overlay (OPTIONAL)
If flickering persists, consider:
```javascript
<Page
  pageNumber={pageNumber}
  width={pageWidth}
  devicePixelRatio={pixelRatio}
  renderMode="canvas"
  renderAnnotationLayer={false}
  renderTextLayer={false} // Disable text layer overlay
/>
```

This sacrifices text selection capability but eliminates layer sync issues.

---

## CSS-Related Issues

No CSS animations or transitions are directly applied to `.pdf-viewer-canvas` or `.report-pdf-card` that would cause flickering. However, the parent `.report-stage-card` has:

```css
.report-stage-card {
  background: var(--color-bg-secondary);
  border: 1px solid rgba(0, 217, 255, 0.12);
  /* No transitions */
}
```

No flickering issues here.

---

## Summary

| Issue | Severity | Root Cause | Impact |
|-------|----------|-----------|--------|
| pixelRatio empty deps | 🔴 Critical | Canvas resolution mismatch | Heavy flickering on load |
| ResizeObserver cascade | 🟠 High | Multiple re-renders during load | Flickering during initialization |
| Page not memoized | 🟠 High | Unnecessary canvas redraws | Selection flickering |
| Selection triggers update | 🟠 High | Parent state updates canvas | Selection flickering |
| Text layer sync | 🟡 Low | Async layer rendering | Minor visual artifacts |

---

## Testing the Fix

After applying Fix 1, test:
1. Load PDF - should render smoothly without flicker
2. Select text - should not cause canvas flicker
3. Zoom in/out - should be smooth
4. Resize window - should debounce updates smoothly
