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
    def extract_pincode(address: str) -> str:
        """Extract a 6-digit Indian PIN code from an address string."""
        if not address:
            return ""
        import re
        match = re.search(r'\b\d{6}\b', address)
        return match.group(0) if match else ""


class SchemaMapper:
    """
    Transforms Fabric-canonical events into target-specific formats.
    This simulates the Mappings stored in the `schema_mappings` database table.
    """
    
    # In production, these mappings are fetched from PostgreSQL `schema_mappings`
    MAPPINGS = {
        "FACTORIES": {
            "business_name": {"target_field": "factory_name", "transform": TransformationRules.uppercase},
            "registered_address": {"target_field": "factory_address", "transform": None},
            "registration_date": {"target_field": "established_date", "transform": TransformationRules.date_iso_to_dd_mm_yyyy},
        },
        "SHOP_ESTABLISHMENT": {
            "business_name": {"target_field": "shop_title", "transform": None},
            "registered_address": {"target_field": "address_line_1", "transform": None},
            # Map pincode dynamically from the registered address
            "pincode_extraction": {
                "source_field": "registered_address",
                "target_field": "postal_code",
                "transform": TransformationRules.extract_pincode
            }
        }
    }

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
                
                # Apply transformation if one exists
                if rule.get("transform") and new_val:
                    try:
                        new_val = rule["transform"](new_val)
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

        # Process derived mappings (e.g. extracting a pincode from the address)
        for rule_name, rule in mapping_def.items():
            if isinstance(rule, dict) and "source_field" in rule:
                source_field = rule["source_field"]
                # Find if the source field was changed in this event
                source_change = next((fc for fc in event.field_changes if fc.field_name == source_field), None)
                if source_change and source_change.new_value:
                    try:
                        derived_val = rule["transform"](source_change.new_value)
                        mapped_changes.append({
                            "field": rule["target_field"],
                            "value": derived_val
                        })
                    except Exception as e:
                        logger.warning("derived_schema_transform_failed", rule=rule_name, error=str(e))

        target_payload["changes"] = mapped_changes
        return target_payload
