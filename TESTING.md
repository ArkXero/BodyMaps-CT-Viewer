# Verification

Full local gate:

```sh
./scripts/check.sh
```

Tests use deterministic temporary NIfTI bundles and isolated artifact directories. Coverage includes:

- Bundle extraction and structured outputs
- Archive path-traversal rejection
- Browser upload validation
- Upload size enforcement
- Async job completion through API
- Dice/IoU scoring against provided masks
- Tri-planar PNG rendering
- External prototype crash capture
- SuPreM input-layout normalization
- Doctor warning/error behavior

Manual browser check:

```sh
uv run bodymaps serve
```

1. Open <http://127.0.0.1:8000>.
2. Run doctor; expect no errors and warnings that bundle mode is not live SuPreM.
3. Run provided sample.
4. Confirm job completes and three slice planes render with overlays.
5. Move each slider and toggle segmentation overlay.
6. Download execution trace and structured result.
