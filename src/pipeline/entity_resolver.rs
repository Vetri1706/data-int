use crate::models::StructuredRecord;
use std::collections::HashMap;

pub struct EntityResolver;

impl EntityResolver {
    pub fn resolve_and_deduplicate(records: Vec<StructuredRecord>) -> Vec<StructuredRecord> {
        let mut canonical_groups: HashMap<String, StructuredRecord> = HashMap::new();

        for record in records {
            let canonical_key = extract_canonical_key(&record.title, &record.canonical_name);

            if let Some(existing) = canonical_groups.get_mut(&canonical_key) {
                // Merge sightings: boost cross_source_agreement
                existing.confidence.cross_source_agreement = (existing.confidence.cross_source_agreement + 0.08).min(0.99);
                existing.confidence.composite_score = (
                    0.30 * existing.confidence.source_authority
                    + 0.25 * existing.confidence.extraction_certainty
                    + 0.20 * existing.confidence.cross_source_agreement
                    + 0.15 * existing.confidence.freshness
                    + 0.10 * existing.confidence.completeness
                ).min(0.99);

                // Merge key attributes
                for (k, v) in record.key_attributes {
                    existing.key_attributes.entry(k).or_insert(v);
                }

                // Merge field evidence
                for (k, v) in record.field_evidence {
                    existing.field_evidence.entry(k).or_insert(v);
                }

                existing.validation_notes.push(format!("Resolved and merged corroborating evidence from {}", record.source_url));
            } else {
                let mut record_clone = record.clone();
                record_clone.canonical_name = canonical_key.clone();
                canonical_groups.insert(canonical_key, record_clone);
            }
        }

        let mut resolved: Vec<StructuredRecord> = canonical_groups.into_values().collect();
        resolved.sort_by(|a, b| b.confidence.composite_score.partial_cmp(&a.confidence.composite_score).unwrap_or(std::cmp::Ordering::Equal));
        resolved
    }
}

fn extract_canonical_key(title: &str, canonical_name: &str) -> String {
    let base = if !canonical_name.trim().is_empty() {
        canonical_name
    } else {
        title
    };

    // Strip common portal suffixes and corporation noise
    let cleaned = base
        .split(" - ")
        .next().unwrap_or(base)
        .split(" | ")
        .next().unwrap_or(base)
        .trim();

    let noise_words = vec![
        "inc", "corp", "corporation", "ltd", "pvt", "limited", "company", "co", "llc", "technologies",
    ];

    let mut words: Vec<&str> = cleaned.split_whitespace().collect();
    words.retain(|w| !noise_words.contains(&w.to_lowercase().trim_matches('.').trim_matches(',')));

    let key = words.join(" ");
    if key.is_empty() {
        base.to_string()
    } else {
        key
    }
}
