"""
UBID Fabric — Schema Mapping Engine (L4)
Handles structural transformations between the generic fabric schema and target specific schemas.
"""

from typing import Any, Callable, Dict, List
import datetime
import structlog

from ubid_fabric.models import CanonicalEvent, FieldChange

logger = structlog.get_logger()

class TransformationRules:
    """Built-in library of data transformation operations."""
    
    @staticmethod
    def date_iso_to_dd_mm_yyyy(value: str) -> str:
        """Convert 'YYYY-MM-DD' to 'DD/MM/YYYY'"""
        if not value:
            return value
        try:
            if "T" in value:
                value = value.split("T")[0]
            dt = datetime.datetime.strptime(value, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            return value

    @staticmethod
    def uppercase(value: str) -> str:
        return value.upper() if isinstance(value, str) else value

    @staticmethod
    def lowercase(value: str) -> str:
        return value.lower() if isinstance(value, str) else value

    @staticmethod
    def concat(*args: Any) -> str:
        """Concatenate multiple values with a space separator."""
        return " ".join(str(a) for a in args if a is not None)

    @staticmethod
    def extract_pincode(address: str) -> str:
        """Extract a 6-digit Indian PIN code from an address string."""
        if not address:
            return ""
        import re
        match = re.search(r'\b\d{6}\b', address)
        return match.group(0) if match else ""

    @staticmethod
    def conditional_status(value: Any) -> str:
        """Map heterogeneous status codes to standard 'ACTIVE'/'INACTIVE'."""
        mapping = {
            "A": "ACTIVE", "1": "ACTIVE", "LIVE": "ACTIVE", "OPEN": "ACTIVE",
            "I": "INACTIVE", "0": "INACTIVE", "CLOSED": "INACTIVE", "REJECTED": "INACTIVE"
        }
        val_str = str(value).upper().strip()
        return mapping.get(val_str, "PENDING")

    @staticmethod
    def format_phone(value: str) -> str:
        """Normalize phone numbers to +91-XXXXXXXXXX format."""
        if not value: return ""
        import re
        digits = re.sub(r'\D', '', value)
        if len(digits) == 10:
            return f"+91-{digits}"
        elif len(digits) == 12 and digits.startswith("91"):
            return f"+91-{digits[2:]}"
        return value


class SchemaMapper:
    """
    Transforms Fabric-canonical events into target-specific formats.
    This simulates the Mappings stored in the `schema_mappings` database table.
    """
    
    # In production, these mappings are fetched from PostgreSQL `schema_mappings`
    MAPPINGS = {
        "SWS": {
            "business_name": {"target_field": "entity_name", "transform": None},
            "registered_address": {"target_field": "primary_address", "transform": None},
            "registration_date": {"target_field": "reg_date", "transform": "date_iso_to_dd_mm_yyyy"},
            "licence_status": {"target_field": "current_status", "transform": "conditional_status"},
            "owner_name": {"target_field": "proprietor_name", "transform": None},
            "contact_phone": {"target_field": "phone", "transform": "format_phone"},
        },
        "FACTORIES": {
            "business_name": {"target_field": "factory_name", "transform": "uppercase"},
            "registered_address": {"target_field": "factory_address", "transform": None},
            "registration_date": {"target_field": "established_date", "transform": "date_iso_to_dd_mm_yyyy"},
            "licence_status": {"target_field": "status", "transform": "conditional_status"},
            "employee_count": {"target_field": "num_workers", "transform": None},
            "pincode": {
                "source_field": "registered_address",
                "target_field": "pin_code",
                "transform": "extract_pincode"
            }
        },
        "SHOP_ESTABLISHMENT": {
            "business_name": {"target_field": "shop_title", "transform": None},
            "registered_address": {"target_field": "address_line_1", "transform": None},
            "owner_name": {"target_field": "proprietor", "transform": None},
            "pincode": {
                "source_field": "registered_address",
                "target_field": "postal_code",
                "transform": "extract_pincode"
            }
        },
        "LABOUR": {
            "business_name": {"target_field": "establishment_name", "transform": None},
            "registered_address": {"target_field": "workplace_address", "transform": None},
            "employee_count": {"target_field": "total_employees", "transform": None},
            "licence_status": {"target_field": "registration_status", "transform": "conditional_status"},
            "contact_phone": {"target_field": "contact_number", "transform": "format_phone"},
        },
        "COMMERCIAL_TAXES": {
            "business_name": {"target_field": "dealer_name", "transform": "uppercase"},
            "registered_address": {"target_field": "place_of_business", "transform": None},
            "licence_status": {"target_field": "gst_status", "transform": "conditional_status"},
        },
    }

    def _get_transform(self, name: str | None) -> Callable | None:
        if not name: return None
        return getattr(TransformationRules, name, None)

    def map_event_for_target(self, target_system: str, event: CanonicalEvent) -> Dict[str, Any]:
        """
        Takes a canonical event and translates its field changes into the exact
        JSON shape required by the target system API.
        """
        mapping_def = self.MAPPINGS.get(target_system, {})
        
        # Default payload base
        target_payload = {
            "ubid": event.ubid,
            "event_id": event.event_id,
            "lamport_timestamp": event.lamport_timestamp,
            "changes": []
        }

        # If no mapping is defined, we pass through the fields exactly as they are
        if not mapping_def:
            target_payload["changes"] = [
                {"field": fc.field_name, "value": fc.new_value}
                for fc in event.field_changes
            ]
            return target_payload

        # Apply schema mappings and transformations
        mapped_changes = []
        
        # Track mapped fields to avoid double-processing
        processed_fields = set()

        for fc in event.field_changes:
            if fc.field_name in mapping_def:
                rule = mapping_def[fc.field_name]
                new_val = fc.new_value
                
                # Apply transformation
                transform_name = rule.get("transform")
                transform_func = self._get_transform(transform_name)
                
                if transform_func and new_val:
                    try:
                        new_val = transform_func(new_val)
                    except Exception as e:
                        logger.warning("schema_transform_failed", field=fc.field_name, error=str(e))
                
                mapped_changes.append({
                    "field": rule.get("target_field", fc.field_name),
                    "value": new_val
                })
                processed_fields.add(fc.field_name)
            else:
                # Unmapped fields are passed through
                mapped_changes.append({
                    "field": fc.field_name,
                    "value": fc.new_value
                })

        # Process derived mappings
        for rule_name, rule in mapping_def.items():
            if isinstance(rule, dict) and "source_field" in rule:
                source_field = rule["source_field"]
                source_change = next((fc for fc in event.field_changes if fc.field_name == source_field), None)
                if source_change and source_change.new_value:
                    try:
                        transform_func = self._get_transform(rule.get("transform"))
                        if transform_func:
                            derived_val = transform_func(source_change.new_value)
                            mapped_changes.append({
                                "field": rule["target_field"],
                                "value": derived_val
                            })
                    except Exception as e:
                        logger.warning("derived_schema_transform_failed", rule=rule_name, error=str(e))

        target_payload["changes"] = mapped_changes
        return target_payload

    def map_incoming_to_canonical(self, source_system: str, changes: List[Dict[str, Any]]) -> List[FieldChange]:
        """
        Translates a department-specific incoming payload into the Fabric's canonical schema.
        Reverse of map_event_for_target.
        """
        mapping_def = self.MAPPINGS.get(source_system, {})
        if not mapping_def:
            return [FieldChange(field_name=c["field"], value=c["value"]) for c in changes]

        # Build inversion map (target_field -> canonical_field)
        inversion = {}
        for canonical_key, rules in mapping_def.items():
            if isinstance(rules, dict):
                target_key = rules.get("target_field")
                if target_key:
                    inversion[target_key] = canonical_key

        canonical_changes = []
        for change in changes:
            source_field = change["field"]
            val = change["value"]
            canonical_field = inversion.get(source_field, source_field)
            canonical_changes.append(FieldChange(field_name=canonical_field, value=val))
            
        return canonical_changes
