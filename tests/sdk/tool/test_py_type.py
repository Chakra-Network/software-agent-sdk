"""Tests for py_type function in openhands.sdk.tool.schema."""

from typing import Any

from openhands.sdk.tool.schema import py_type


class TestPyTypePrimitiveTypes:
    """Test py_type with primitive JSON schema types."""

    def test_string_type(self):
        """Test that string type maps to Python str."""
        # Arrange
        spec = {"type": "string"}

        # Act
        result = py_type(spec)

        # Assert
        assert result is str

    def test_integer_type(self):
        """Test that integer type maps to Python int."""
        # Arrange
        spec = {"type": "integer"}

        # Act
        result = py_type(spec)

        # Assert
        assert result is int

    def test_number_type(self):
        """Test that number type maps to Python float."""
        # Arrange
        spec = {"type": "number"}

        # Act
        result = py_type(spec)

        # Assert
        assert result is float

    def test_boolean_type(self):
        """Test that boolean type maps to Python bool."""
        # Arrange
        spec = {"type": "boolean"}

        # Act
        result = py_type(spec)

        # Assert
        assert result is bool


class TestPyTypeObjectType:
    """Test py_type with object type."""

    def test_object_type(self):
        """Test that object type maps to dict[str, Any]."""
        # Arrange
        spec = {"type": "object"}

        # Act
        result = py_type(spec)

        # Assert
        assert result == dict[str, Any]


class TestPyTypeArrayType:
    """Test py_type with array types."""

    def test_array_without_items(self):
        """Test that array without items returns list[Any]."""
        # Arrange
        spec = {"type": "array"}

        # Act
        result = py_type(spec)

        # Assert
        assert result == list[Any]

    def test_array_with_dict_items(self):
        """Test that array with dict items recursively processes inner type."""
        # Arrange
        spec = {"type": "array", "items": {"type": "string"}}

        # Act
        result = py_type(spec)

        # Assert
        assert result == list[str]

    def test_array_with_nested_array(self):
        """Test that array with nested array processes correctly."""
        # Arrange
        spec = {
            "type": "array",
            "items": {"type": "array", "items": {"type": "integer"}},
        }

        # Act
        result = py_type(spec)

        # Assert
        assert result == list[list[int]]

    def test_array_with_non_dict_items(self):
        """Test that array with non-dict items returns list[Any]."""
        # Arrange
        spec = {"type": "array", "items": "string"}

        # Act
        result = py_type(spec)

        # Assert
        assert result == list[Any]


class TestPyTypeUnionTypes:
    """Test py_type with union types (list/tuple/set)."""

    def test_union_list_with_single_non_null(self):
        """Test that union list with single non-null type extracts that type."""
        # Arrange
        spec = {"type": ["string", "null"]}

        # Act
        result = py_type(spec)

        # Assert
        assert result is str

    def test_union_tuple_with_single_non_null(self):
        """Test that union tuple with single non-null type extracts that type."""
        # Arrange
        spec = {"type": ("integer", "null")}

        # Act
        result = py_type(spec)

        # Assert
        assert result is int

    def test_union_set_with_single_non_null(self):
        """Test that union set with single non-null type extracts that type."""
        # Arrange
        spec = {"type": {"number", "null"}}

        # Act
        result = py_type(spec)

        # Assert
        assert result is float

    def test_union_with_multiple_non_null_types(self):
        """Test that union with multiple non-null types returns Any."""
        # Arrange
        spec = {"type": ["string", "integer"]}

        # Act
        result = py_type(spec)

        # Assert
        assert result is Any

    def test_union_with_only_null(self):
        """Test that union with only null type returns Any."""
        # Arrange
        spec = {"type": ["null"]}

        # Act
        result = py_type(spec)

        # Assert
        assert result is Any

    def test_union_with_three_types_one_null(self):
        """Test that union with three types where one is null extracts non-null."""
        # Arrange
        spec = {"type": ["boolean", "null", "string"]}

        # Act
        result = py_type(spec)

        # Assert
        assert result is Any


class TestPyTypeEdgeCases:
    """Test py_type with edge cases and invalid inputs."""

    def test_missing_type_key(self):
        """Test that missing type key returns Any."""
        # Arrange
        spec = {}

        # Act
        result = py_type(spec)

        # Assert
        assert result is Any

    def test_unknown_type(self):
        """Test that unknown type returns Any."""
        # Arrange
        spec = {"type": "unknown_type"}

        # Act
        result = py_type(spec)

        # Assert
        assert result is Any

    def test_empty_dict(self):
        """Test that empty dict returns Any."""
        # Arrange
        spec = {}

        # Act
        result = py_type(spec)

        # Assert
        assert result is Any

    def test_type_none(self):
        """Test that type=None returns Any."""
        # Arrange
        spec = {"type": None}

        # Act
        result = py_type(spec)

        # Assert
        assert result is Any

    def test_array_with_empty_items_dict(self):
        """Test that array with empty items dict returns list[Any]."""
        # Arrange
        spec = {"type": "array", "items": {}}

        # Act
        result = py_type(spec)

        # Assert
        assert result == list[Any]


class TestPyTypeRefResolution:
    """Test py_type with $ref / $defs resolution."""

    def test_ref_to_scalar_def_is_resolved(self):
        """A $ref to a scalar def resolves to that scalar type."""
        defs = {"MyStr": {"type": "string"}}
        spec = {"$ref": "#/$defs/MyStr"}

        result = py_type(spec, defs)

        assert result is str

    def test_array_of_ref_items_resolves_inner_type(self):
        """list[ref → string] becomes list[str]."""
        defs = {"MyStr": {"type": "string"}}
        spec = {"type": "array", "items": {"$ref": "#/$defs/MyStr"}}

        result = py_type(spec, defs)

        assert result == list[str]

    def test_ref_to_object_with_properties_builds_nested_model(self):
        """A $ref to an object def builds a Pydantic model with the props."""
        defs = {
            "Block": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["a", "b"]},
                    "n": {"type": "integer"},
                },
                "required": ["kind"],
            }
        }
        spec = {"type": "array", "items": {"$ref": "#/$defs/Block"}}

        result = py_type(spec, defs)

        # list[<NestedModel>]
        assert getattr(result, "__origin__", None) is list
        (inner,) = result.__args__
        # The inner type is a Pydantic BaseModel with both fields.
        json_schema = inner.model_json_schema()
        assert "kind" in json_schema["properties"]
        assert "n" in json_schema["properties"]
        assert json_schema["properties"]["kind"]["enum"] == ["a", "b"]
        assert json_schema["required"] == ["kind"]

    def test_self_referential_ref_falls_back_to_dict(self):
        """A self-referential $ref cycle falls back to dict[str, Any]."""
        # Block.children → list[Block] (recursive)
        defs = {
            "Block": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "children": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/Block"},
                    },
                },
            }
        }
        spec = {"$ref": "#/$defs/Block"}

        result = py_type(spec, defs)

        # Outer is a Pydantic model — accessing model_json_schema below should
        # not RecursionError on the self-referential children field.
        json_schema = result.model_json_schema()
        # children is optional → Pydantic represents it as anyOf[array, null].
        children_schema = json_schema["properties"]["children"]
        if "anyOf" in children_schema:
            array_variant = next(
                v for v in children_schema["anyOf"] if v.get("type") == "array"
            )
        else:
            array_variant = children_schema
        assert array_variant["type"] == "array"

    def test_missing_def_for_ref_returns_any(self):
        """A $ref pointing to a missing def falls through to Any."""
        # No defs supplied → ref can't be resolved → behaves like an empty spec.
        spec = {"$ref": "#/$defs/MissingDef"}

        result = py_type(spec, {})

        assert result is Any

    def test_backward_compatible_single_arg(self):
        """Existing single-arg callers continue to work."""
        spec = {"type": "string"}
        # Same as test_string_type but explicitly asserting no positional
        # break for downstream callers.
        assert py_type(spec) is str
