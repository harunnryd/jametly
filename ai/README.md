# jamly — Python AI sidecar

Phase 0 scaffold. Single NDJSON-stdin / NDJSON-stdout process. Exposes an `echo` method and an error envelope for everything else.

## Run manually

```bash
cd /Users/pushmove/Desktop/tools/goddamn/jametly
echo '{"id":"r1","method":"echo","params":{"x":"hi"}}' | uv run --project ai python -m jamly
```

Expect:

```json
{"id":"r1","result":{"x":"hi"}}
```
