# ACL_9TH

Formula 1 coursework, organized by milestone:

- [MS1/M1.ipynb](MS1/M1.ipynb): the original Milestone 1 analysis and machine-learning notebook, moved without changing its contents.
- [MS2/README.md](MS2/README.md): Milestone 2 Python/Neo4j knowledge graph, five Cypher queries, setup instructions and tests.

```text
ACL_9TH/
├── MS1/
│   └── M1.ipynb
├── MS2/
│   ├── Create_kg.py
│   ├── queries.txt
│   ├── config.example.txt
│   ├── requirements.txt
│   ├── download_data.py
│   ├── run_queries.py
│   ├── data_manifest.json
│   ├── compose.yaml
│   ├── tests/
│   ├── verification/
│   ├── VALIDATION.md
│   └── README.md
└── README.md
```

MS2's nine CSVs and local `config.txt` sit beside `Create_kg.py` at runtime and are
ignored in Git. The version-pinned downloader reproduces the CSVs. All implementation
work is isolated on `feature/milestone-2-knowledge-graph`; `main` is not merged or modified.
