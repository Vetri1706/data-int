use crate::models::StructuredRecord;

pub struct DatasetExporter;

impl DatasetExporter {
    pub fn to_csv(records: &[StructuredRecord]) -> String {
        if records.is_empty() {
            return "ID,Canonical_Name,Title,Category,Validation_Status,Composite_Confidence,Source_Authority,Extraction_Certainty,Source_Type,Source_URL\n".to_string();
        }

        let mut csv = String::new();
        csv.push_str("ID,Canonical_Name,Title,Category,Validation_Status,Composite_Confidence,Source_Authority,Extraction_Certainty,Source_Type,Source_URL,Domain,Citation_Anchor,Snippet_Preview\n");

        for r in records {
            let domain = r.key_attributes.get("domain").cloned().unwrap_or_default();
            let anchor = r.key_attributes.get("anchor_citation").cloned().unwrap_or_default();
            let snippet = r.key_attributes.get("snippet_preview").cloned().unwrap_or_default();

            csv.push_str(&format!(
                "\"{}\",\"{}\",\"{}\",\"{}\",\"{}\",{:.3},{:.2},{:.2},\"{}\",\"{}\",\"{}\",\"{}\",\"{}\"\n",
                r.id,
                escape_csv(&r.canonical_name),
                escape_csv(&r.title),
                escape_csv(&r.category),
                escape_csv(&r.validation_status),
                r.confidence.composite_score,
                r.confidence.source_authority,
                r.confidence.extraction_certainty,
                escape_csv(&r.source_type),
                escape_csv(&r.source_url),
                escape_csv(&domain),
                escape_csv(&anchor),
                escape_csv(&snippet)
            ));
        }

        csv
    }

    pub fn to_json(records: &[StructuredRecord]) -> String {
        serde_json::to_string_pretty(records).unwrap_or_else(|_| "[]".to_string())
    }
}

fn escape_csv(val: &str) -> String {
    val.replace('"', "\"\"").replace('\n', " ").replace('\r', "")
}
