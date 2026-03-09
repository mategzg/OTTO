#!/usr/bin/env python3
import subprocess
from pathlib import Path

BASE = Path("data/rag_eval")
BASE.mkdir(parents=True, exist_ok=True)

# dataset with leakage boundaries
(BASE / "sg_peer_a.txt").write_text("SKU-MEL-123 precio especial peer A. Cliente ACME.")
(BASE / "sg_peer_a_2.txt").write_text("Condición comercial: melamina se actualiza semanalmente.")


def run(cmd):
    return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)


def main():
    run(
        "python3 free_stack/rag/build_rag_index.py --input-dir data/rag_eval --collection rag_eval "
        "--audience staff --domain sg --channel whatsapp --peer-id peerA --thread-id none --doc-type note"
    )

    keyword = run(
        "python3 free_stack/rag/query_rag.py --collection rag_eval --query 'SKU-MEL-123' "
        "--audience staff --domain sg --channel whatsapp --peer_id peerA --top-k-final 3"
    )
    semantic = run(
        "python3 free_stack/rag/query_rag.py --collection rag_eval --query 'precio especial de melamina' "
        "--audience staff --domain sg --channel whatsapp --peer_id peerA --top-k-final 3"
    )
    no_leak = run(
        "python3 free_stack/rag/query_rag.py --collection rag_eval --query 'SKU-MEL-123' "
        "--audience staff --domain sg --channel whatsapp --peer_id peerB --top-k-final 3"
    )

    print("KEYWORD_TEST_OK" if "SKU-MEL-123" in keyword else "KEYWORD_TEST_FAIL")
    print("SEMANTIC_TEST_OK" if "precio especial" in semantic.lower() else "SEMANTIC_TEST_FAIL")
    print("NO_LEAK_TEST_OK" if "NO_VERIFICADO" in no_leak else "NO_LEAK_TEST_FAIL")


if __name__ == "__main__":
    main()
