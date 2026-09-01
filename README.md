# CipherNova

CipherNova is a sophisticated GenLayer Intelligent Contract designed for deterministically evaluating the consistency of bounded external records. By leveraging the Equivalence Principle and Optimistic Democracy on the GenLayer protocol, CipherNova ensures that disparate data sources can be materially compared against a declared claim.

**Deployed Contract Address (GenLayer Studio):** `0xE5ea5f5ff4d2cE92f86C539AA757E2e06a76912B`

## Overview

CipherNova addresses a core problem in decentralized ecosystems: ensuring that multiple bounded representations of a fact (like documentation, API responses, public configurations) agree with each other without forcing a single "winner." 

It operates by:
1. Taking 2 to 5 ordered textual records representing the same subject.
2. Independently fetching and validating all sources securely.
3. Generating unique pairs and conducting strict semantic evaluations of their consistency.
4. Projecting the pairwise findings into a deterministic overall conclusion (`CONSISTENT`, `INCONSISTENT`, or `UNRESOLVED`).

## Architecture & Integration

CipherNova runs in GenLayer's consensus boundary, ensuring that both leaders and validators independently build proposals and re-fetch resources. It strictly prohibits the LLM evaluator from injecting opinions, recommending values, or determining the final status. The evaluation outcome is 100% deterministic based strictly on the semantic comparison of provided texts.

### Lifecycle

- **Creation**: `create_case(case_json)` accepts normalized case parameters and stores them immutably.
- **Evaluation**: `evaluate(case_id)` independently fetches data, parses pairwise consistency via GenVM AI execution, and concludes the final status.
- **Retry**: Transient network errors can be retried using `retry_evaluation(case_id)`.

### Schemas
Input configurations and cases must strictly adhere to the defined JSON schemas found in the `schemas/` directory to prevent injection and oversized context boundaries.

## Testing & Local Development

The contract comes with a comprehensive test suite covering direct behavioral unit testing and simulated validator consensus.

To run the tests:
```bash
pytest tests/direct -q
pytest tests/consensus -q
```

To run linting and typechecking locally via the GenVM Linter:
```bash
genvm-lint check contract/CipherNova.py
genvm-lint typecheck contract/CipherNova.py
```

## Security & Limitations

CipherNova focuses exclusively on verifying consistency across a creator-selected record set. It does *not* prove that the selected records are inherently truthful, independently hosted, or authoritative. Developers integrating CipherNova should enforce provenance and domain policies at the application layer before feeding URLs into the intelligent contract.
