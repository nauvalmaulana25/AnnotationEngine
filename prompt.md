Okay, I just tried running it locally. Before successfully calling the model, I encountered several 404 warnings
(venv) nauval@nauval-ASUS-TUF-Gaming-A15-FA506QM-FA506QM:~/Documents/Annotation_Engine$ python -m annotation_engine.main
2026-11-24 10:57:51,837 - __main__ - INFO - Starting AnnotationEngine v1.0.0
2026-11-24 10:57:51,911 - annotation_engine.core.database - INFO - Database initialized at /home/nauval/.local/share/AnnotationEngine/annotation_engine.db
2026-11-24 10:57:51,911 - __main__ - INFO - Database initialized
2026-11-24 10:57:51,911 - __main__ - INFO - Encryption manager initialized
2026-11-24 10:58:44,666 - __main__ - INFO - Application started successfully
2026-11-24 11:00:14,441 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/processor_config.json "HTTP/1.1 404 Not Found"
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
2026-11-24 11:00:14,441 - huggingface_hub.utils._http - WARNING - Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
2026-11-24 11:00:14,760 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/preprocessor_config.json "HTTP/1.1 307 Temporary Redirect"
2026-11-24 11:00:14,793 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/api/resolve-cache/models/IDEA-Research/grounding-dino-tiny/a2bb814dd30d776dcf7e30523b00659f4f141c71/preprocessor_config.json "HTTP/1.1 200 OK"
2026-11-24 11:00:15,059 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/processor_config.json "HTTP/1.1 404 Not Found"
2026-11-24 11:00:15,324 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/preprocessor_config.json "HTTP/1.1 307 Temporary Redirect"
2026-11-24 11:00:15,335 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/api/resolve-cache/models/IDEA-Research/grounding-dino-tiny/a2bb814dd30d776dcf7e30523b00659f4f141c71/preprocessor_config.json "HTTP/1.1 200 OK"
2026-11-24 11:00:15,621 - httpx - INFO - HTTP Request: GET https://huggingface.co/api/models/IDEA-Research/grounding-dino-tiny/tree/main/additional_chat_templates?recursive=false&expand=false "HTTP/1.1 404 Not Found"
2026-11-24 11:00:15,884 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/processor_config.json "HTTP/1.1 404 Not Found"
2026-11-24 11:00:16,156 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/chat_template.json "HTTP/1.1 404 Not Found"
2026-11-24 11:00:16,409 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/chat_template.jinja "HTTP/1.1 404 Not Found"
2026-11-24 11:00:16,698 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/audio_tokenizer_config.json "HTTP/1.1 404 Not Found"
2026-11-24 11:00:16,974 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/processor_config.json "HTTP/1.1 404 Not Found"
2026-11-24 11:00:17,234 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/preprocessor_config.json "HTTP/1.1 307 Temporary Redirect"
2026-11-24 11:00:17,247 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/api/resolve-cache/models/IDEA-Research/grounding-dino-tiny/a2bb814dd30d776dcf7e30523b00659f4f141c71/preprocessor_config.json "HTTP/1.1 200 OK"
2026-11-24 11:00:17,525 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/processor_config.json "HTTP/1.1 404 Not Found"
2026-11-24 11:00:17,788 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/preprocessor_config.json "HTTP/1.1 307 Temporary Redirect"
2026-11-24 11:00:17,802 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/api/resolve-cache/models/IDEA-Research/grounding-dino-tiny/a2bb814dd30d776dcf7e30523b00659f4f141c71/preprocessor_config.json "HTTP/1.1 200 OK"
2026-11-24 11:00:18,055 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/config.json "HTTP/1.1 307 Temporary Redirect"
2026-11-24 11:00:18,065 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/api/resolve-cache/models/IDEA-Research/grounding-dino-tiny/a2bb814dd30d776dcf7e30523b00659f4f141c71/config.json "HTTP/1.1 200 OK"
2026-11-24 11:00:18,354 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/tokenizer_config.json "HTTP/1.1 307 Temporary Redirect"
2026-11-24 11:00:18,365 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/api/resolve-cache/models/IDEA-Research/grounding-dino-tiny/a2bb814dd30d776dcf7e30523b00659f4f141c71/tokenizer_config.json "HTTP/1.1 200 OK"
2026-11-24 11:00:18,625 - httpx - INFO - HTTP Request: GET https://huggingface.co/api/models/IDEA-Research/grounding-dino-tiny/tree/main/additional_chat_templates?recursive=false&expand=false "HTTP/1.1 404 Not Found"
2026-11-24 11:00:18,901 - httpx - INFO - HTTP Request: GET https://huggingface.co/api/models/IDEA-Research/grounding-dino-tiny/tree/main?recursive=true&expand=false "HTTP/1.1 200 OK"
2026-11-24 11:00:19,183 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/IDEA-Research/grounding-dino-tiny/resolve/main/config.json "HTTP/1.1 307 Temporary Redirect"
2026-11-24 11:00:19,198 - httpx - INFO - HTTP Request: HEAD https://huggingface.co/api/resolve-cache/models/IDEA-Research/grounding-dino-tiny/a2bb814dd30d776dcf7e30523b00659f4f141c71/config.json "HTTP/1.1 200 OK"
Loading weights: 100%|██████████████████████████████████████████████████████████████████████████| 990/990 [00:00<00:00, 3529.26it/s]
. Are these a cause for concern? If so, what is the underlying cause? Please conduct a root cause analysis.