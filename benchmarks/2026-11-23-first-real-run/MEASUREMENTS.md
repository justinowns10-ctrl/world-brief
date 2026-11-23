# Benchmark: first real run, 2026-11-23

Measurements only. The briefing, claims, run log and source records this run produced are kept beside this file on the desktop and are not in Git (see `.gitignore`).

| | |
|---|---|
| Host | Windows-11-10.0.26300-SP0, Python 3.14.10 |
| Model | `openai/gpt-oss-20b` (20B, MXFP4, 4 bits per weight, gguf, 12.1 GB) |
| Load settings | context 8192 of 131072, parallel slots 4, flash attention True, eval batch 2048, KV cache on GPU True |
| Backend settings | temperature 0.1, max output tokens 2000, prompt cap 14000 characters, one request at a time |
| Embedding model | none (word-overlap clustering) |
| Feeds | 6 read, 0 failed, 170 new articles, 97 in the window |
| Events | 74 clusters; {'selected': 12, 'processed': 12, 'published': 12, 'skippedUnsupported': 0, 'skippedErrors': 0, 'unprocessed': 0} |
| Wall time | 117.2 s |
| Inference | 26 calls, 90.0 s |
| GPU | NVIDIA GeForce RTX 5070 Ti: peak 13591 of 16303 MiB (start 13504), load peak 63 %, 60 C |
| System memory | peak 33685 of 97663 MiB (start 33190), CPU peak 46.5 % |
| Claims | 29 drafted, 26 published (5 partly confirmed), 3 removed; verdicts {'unsupported': 3, 'supported': 21, 'partial': 5} |
| Stories | 12: {'verified': 2, 'preliminary': 9, 'disputed': 1} |
| State | complete |

| Task | Calls | Failed | Mean s | Max s | Prompt tokens | Output tokens | Output tokens/s |
|---|---|---|---|---|---|---|---|
| rank | 2 | 0 | 11.97 | 13.684 | 1886 | 2945 | 123.0 |
| summarize | 12 | 0 | 2.325 | 3.163 | 5807 | 3241 | 116.2 |
| verify | 12 | 0 | 3.18 | 5.157 | 6209 | 4657 | 122.0 |

Resource figures are for the whole machine, sampled every 2 s, and include anything else that was running.
