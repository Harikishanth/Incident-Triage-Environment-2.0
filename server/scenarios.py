"""
Incident Scenarios (V2: State-Machine Environment)
"""

EASY_SCENARIOS = [
    {
        "id": "easy_db_exhaustion_001",
        "description": "PaymentService connection pool exhaustion.",
        "alert": "[P2 ALERT] PaymentService API responding with 500s. High latency detected.",
        "logs": {
            "PaymentService": [
                "[02:45 UTC] [INFO] Processing charge request",
                "[02:46 UTC] [ERROR] Timeout waiting for connection from pool: DatabaseConnectionPool exhausted.",
                "[02:46 UTC] [ERROR] Transaction failed, returning 500"
            ],
            "OrderService": [
                "[02:46 UTC] [WARN] PaymentService failed to respond in 5000ms",
            ]
        },
        "optimal_path": ["PaymentService", "PostgreSQL_connection_pool"],
        "solution": {
            "tool": "apply_fix",
            "target": "PostgreSQL_connection_pool"
        }
    }
]

MEDIUM_SCENARIOS = [
    {
        "id": "medium_cert_expiry_001",
        "description": "Mutal TLS certificate expiration causing inter-service communication failure.",
        "alert": "[P1 ALERT] OrderService failing to communicate with BillingService. 503 Service Unavailable.",
        "logs": {
            "OrderService": [
                "[14:20 UTC] [INFO] Retrieving order details",
                "[14:21 UTC] [ERROR] Upstream failure: BillingService returned 503",
            ],
            "BillingService": [
                "[14:20 UTC] [INFO] Inbound request from OrderService rejected",
                "[14:21 UTC] [FATAL] TLS Handshake failed: x509: certificate has expired or is not yet valid"
            ],
            "ApiGateway": [
                "[14:21 UTC] [WARN] Rate limiting triggered for user IPs"
            ]
        },
        "solution": {
            "tool": "apply_fix",
            "target": "BillingService_TLS_certificate"
        }
    }
]

HARD_SCENARIOS = [
    {
        "id": "hard_cascading_p0_001",
        "description": "Aggressive DB compaction filled WAL archive, crashing primary DB and causing stale read replicas.",
        "alert": "[P0 OUTAGE] Entire platform down. Database unresponsive. Replicas failing over repeatedly.",
        "logs": {
            "PostgresPrimary": [
                "[09:00 UTC] [INFO] Starting aggressive vacuum compaction",
                "[09:05 UTC] [FATAL] pg_wal volume 100% full. No space left on device.",
                "[09:05 UTC] [FATAL] Checkpoint process failed. Stopping DB."
            ],
            "PostgresReplica": [
                "[09:06 UTC] [WARN] Primary unreachable. Initiating failover.",
                "[09:07 UTC] [ERROR] Failover aborted: Replica lag is too high."
            ],
            "WebFrontend": [
                "[09:08 UTC] [ERROR] 500 Internal Server Error. DB connection refused."
            ]
        },
        # For hard, strict ordering is needed
        "ordered_solution": [
            {"tool": "apply_fix", "target": "PostgresPrimary_WAL_volume"},
            {"tool": "apply_fix", "target": "PostgresPrimary"},
            {"tool": "apply_fix", "target": "PostgresReplica_failover"}
        ]
    }
]
