# Claim verification evaluation

Run `python evaluation/run_claim_benchmark.py` from the repository root. No model keys or network are needed. The fixture is `fixtures/claim_adversarial.json`; predictions and timings are written to `results/claim_benchmark.json`.

## What is measured

Forty synthetic, author-labelled subject/field/value/source cases cover wrong locations, wrong quantities, units and currency, dates, negation, certification numbers, nearby entities, unknown values and valid statements. Twenty are known regression cases; twenty are harder challenge cases. Both subsets were visible during development, so neither is an independent holdout.

The baseline is the old lexical `supported()` function frozen from commit `2981853`, not a reconstruction of the entire old pipeline. It has no contradiction class; its rejections map to unknown. Both functions receive identical candidate values and source text. The primary comparison is false support and support precision/recall. Three-state accuracy is reported with this baseline limitation.

| Metric (40 cases) | Lexical baseline | Typed verifier |
| --- | ---: | ---: |
| False accepts | 17 | 0 |
| Supported-claim precision | 46.9% | 100% |
| Supported-claim recall | 83.3% | 77.8% |
| Three-state accuracy | 42.5% | 90% |
| Unknown / abstained | 8 | 17 |

On the challenge subset, typed verification recognizes only 4 of 8 supported claims (50% recall). The current grammar misses valid paraphrases, flexible URL/format variants and some sentence constructions. Zero observed false accepts in 40 synthetic cases is **not** a production accuracy estimate or a guarantee against adversarial text.

## Next validation gate

Use a separately annotated set of real permitted pages with frozen content hashes, candidate identities, field values, required-field labels and adjudicated disagreements. Report field support precision/recall, entity merge errors, accepted-row precision, coverage, abstention, completed/partial/exhausted rates, latency and model-token cost. Keep data acquisition and extraction quality separate from verifier quality.

Laya must stay disabled until an on/off ablation on that same frozen input set demonstrates a predeclared reduction in median extraction cost or latency, with no increase in false support and no loss of accepted-record yield beyond a predeclared tolerance. Repeated runs are needed for latency/model variation. Existing Laya experiments in this directory do not establish those acceptance criteria.
