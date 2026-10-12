# Use-case model

Use `python usecase.py model.json -o new-output` for one subject with 1–12 actors, 1–30 use cases and at most 80 relations. Dependencies are the same pinned `runtime` packages as the class renderer. No browser or API key is needed. One placement, at most 32 route alternatives per relationship, one text-measurement batch and one final PNG; no regenerate-until-pass loop.

```json
{
  "type": "use_case", "name": "Checkout system",
  "actors": [
    {"id": "customer", "name": "Customer", "kind": "human", "side": "left"},
    {"id": "bank", "name": "Payment service", "kind": "external", "side": "right"}
  ],
  "use_cases": [
    {"id": "checkout", "name": "Submit order", "extension_points": ["Apply discount"]},
    {"id": "payment", "name": "Process payment"},
    {"id": "coupon", "name": "Use coupon"}
  ],
  "relations": [
    {"id": "r1", "kind": "association", "source": "customer", "target": "checkout"},
    {"id": "r2", "kind": "association", "source": "bank", "target": "payment"},
    {"id": "r3", "kind": "include", "source": "checkout", "target": "payment"},
    {"id": "r4", "kind": "extend", "source": "coupon", "target": "checkout", "extension_points": ["Apply discount"]}
  ]
}
```

IDs are unique ASCII identifiers starting with a letter. Actor `kind` defaults to `human`; `external` uses a plain `«actor»` rectangle. Actor `side` is a layout hint, defaulting to left for humans and right for external systems. It does not express initiation or navigation.

- `association`: actor/use-case pair in either source order, plain solid line without a navigation arrow.
- `include`: including use case → included use case, dashed open arrow with `«include»`.
- `extend`: extending use case → extended use case, dashed open arrow with `«extend»`. Supply at least one named extension point declared on the target; do not invent it.
- `generalization`: specialized actor/use case → general actor/use case of the same type, solid line and hollow triangle. Include and generalization cycles are rejected.

Up to four named extension points are shown in a use-case compartment. Multiple subjects/packages, conditions/notes, association multiplicities, other stereotypes/members and natural-language requirement certification are outside this version. Unsupported fields are rejected; exact input is preserved in `input-model.json`. Do not add shared login/payment steps or infer includes from chronological order.

`--no-role-order` and `--no-relation-columns` independently disable actor/relationship-component ordering and main/related-use-case columns. These are layout decisions; columns alone can increase crossings. Replicate the fixed factorial with `python benchmarks/usecase_ablation.py -o new-study`.

Read `run.json`, `review.json` and `native-check.json`, then inspect `diagram.png`. Exit 0 means the geometry/native checks passed; 2 means review needed or unsupported/invalid input; 3 means execution failed. Checks do not certify independent requirements, actual browser font bounds or human aesthetics. Dense graphs can retain crossings. The native file supports ordinary edits and attached connectors; class `reflow.py` does not import use cases, and longer native edits are not automatically fitted.

Notation: [OMG UML 2.5.1, §§18.1.3–18.1.4](https://www.omg.org/spec/UML/2.5.1/PDF). Figure 18.10 provided a small role-centered design reference; shipped models and the implementation are original synthetic cases.
