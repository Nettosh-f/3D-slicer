# Part presence policy

A broad artifact class defines the parts that *may* exist, not the parts that must exist.

## Modes

### Conservative default

Used when the user does not select any visible parts.

The v0.2 geometric engine exports only the class primary fallback part:

- pottery → body
- figurine → torso
- lithic → dorsal face
- metalwork → blade/body
- organic → shaft

This prevents fabricated labels on fragments.

### I know which parts are visible

The user selects the parts to export. Use this for sherds/fragments/partial views.

Examples:

```text
pottery sherd: body
pottery rim sherd: rim, neck
figurine fragment: head, face
```

### Force all taxonomy parts

Debug only. Attempts every possible part in the taxonomy. This can create wrong labels and should not be used directly as training data for Tool 3.

## JSON implications

Missing taxonomy parts are not errors. They are recorded in `possible_parts_not_exported`.

Tool 3 should consume the `parts` list as the actual exported part records and should not assume a fixed number of parts per image or artifact.
