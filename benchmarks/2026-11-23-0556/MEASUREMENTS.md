# Measurements: run for 2026-11-23, started 2026-11-23T10:56:13Z

Numbers only. The briefing, claims, run log and source records are kept beside this file on the machine that ran it and are not in Git.

| | |
|---|---|
| Host | Windows-11-10.0.26300-SP0, Python 3.14.10 |
| Pipeline version | 0.1.0 |
| Model | `openai/gpt-oss-20b` (20B, MXFP4, 4 bits per weight, gguf) |
| Load settings | context 8192 of 131072, parallel slots 4, flash attention True |
| Backend settings | temperature 0.1, max output tokens 2000, prompt cap 14000 characters, one request at a time |
| Embedding model | none |
| Feeds | 6 read, 0 failed, 4 new articles, 101 in the window |
| Article kinds | {'analysis': 11, 'news': 78, 'live': 4, 'opinion': 2, 'sport': 6} |
| Events | 53 clusters (names and word overlap); {'selected': 12, 'processed': 12, 'published': 12, 'skippedUnsupported': 0, 'skippedErrors': 0, 'unprocessed': 0} |
| Wall time | 115.8 s |
| Inference | 26 calls, 83.4 s |
| GPU | NVIDIA GeForce RTX 5070 Ti: peak 13739 of 16303 MiB (start 13697), load peak 67 %, 58 C |
| System memory | peak 34027 of 97663 MiB (start 33864), CPU peak 42.6 % |
| Claims | 31 drafted, 30 published (7 partly confirmed), 1 removed; verdicts {'unsupported': 1, 'supported': 23, 'partial': 7} |
| Stories | 12: {'verified': 2, 'preliminary': 9, 'disputed': 1} |
| State | complete |

| Task | Calls | Failed | Mean s | Max s | Prompt tokens | Output tokens | Output tokens/s |
|---|---|---|---|---|---|---|---|
| rank | 2 | 0 | 8.808 | 10.904 | 2027 | 2169 | 123.1 |
| summarize | 12 | 0 | 2.172 | 2.675 | 6684 | 3029 | 116.2 |
| verify | 12 | 0 | 3.307 | 4.809 | 6887 | 4886 | 123.1 |

Resource figures are for the whole machine and include anything else that was running.
