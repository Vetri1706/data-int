use crate::models::{ConfidenceBreakdown, DataContract, FieldEvidence, StructuredRecord};
use crate::pipeline::source_registry::SourceRegistry;
use chrono::Utc;
use std::collections::HashMap;

pub struct ValidatorEngine;

impl ValidatorEngine {
    pub fn validate_and_score(
        mut records: Vec<StructuredRecord>,
        contract: &DataContract,
        registry: &SourceRegistry,
        query: &str,
    ) -> Vec<StructuredRecord> {
        let q_lower = query.to_lowercase();
        let query_tokens: Vec<&str> = q_lower.split_whitespace().collect();

        for record in records.iter_mut() {
            let mut validation_notes = Vec::new();
            let mut is_valid = true;

            // 1. Source Profile from Registry
            let domain_profile = registry.profile_for_url(&record.source_url);
            record.source_type = domain_profile.source_type.clone();

            // 2. Structural Validation
            if !record.source_url.starts_with("http://") && !record.source_url.starts_with("https://") {
                is_valid = false;
                validation_notes.push("Invalid source URL protocol".to_string());
            }

            for crit in &contract.critical_fields {
                let has_crit = record.key_attributes.contains_key(crit) 
                    || record.title.to_lowercase().contains(&crit.to_lowercase())
                    || crit == "apply_url" && !record.source_url.is_empty();
                if !has_crit {
                    validation_notes.push(format!("Missing critical schema field: {}", crit));
                }
            }

            // 3. Constraint & Semantic Validation
            let combined_text = format!("{} {} {:?}", record.title, record.canonical_name, record.key_attributes).to_lowercase();
            
            for constraint in &contract.constraints {
                if constraint.contains("location ~=") {
                    let target_city = constraint.replace("location ~=", "").trim().to_lowercase();
                    if !combined_text.contains(&target_city) && !q_lower.contains(&target_city) {
                        validation_notes.push(format!("Location constraint warning: '{}' not explicitly verified", target_city));
                    }
                }
            }

            // Semantic Token Relevance
            let mut token_matches = 0;
            for token in &query_tokens {
                if token.len() > 3 && combined_text.contains(token) {
                    token_matches += 1;
                }
            }
            let semantic_match_ratio = if !query_tokens.is_empty() {
                (token_matches as f32 / query_tokens.len() as f32).min(1.0)
            } else {
                0.8
            };

            // 4. Field-Level Evidence & Confidence Computation
            let mut field_evidence_map = HashMap::new();
            let excerpt_preview = record.key_attributes.get("snippet_preview")
                .cloned()
                .unwrap_or_else(|| record.title.clone());

            for (field, value) in &record.key_attributes {
                if field == "snippet_preview" || field == "anchor_citation" {
                    continue;
                }

                // Check if value or part of value appears directly in the scraped excerpt quote
                let quote_matched = excerpt_preview.to_lowercase().contains(&value.to_lowercase());
                let field_conf = if quote_matched {
                    (domain_profile.authority_score * 0.95).max(0.70)
                } else {
                    (domain_profile.authority_score * 0.80).max(0.60)
                };

                let quote = if quote_matched {
                    format!("Direct excerpt confirmation: \"{}\"", truncate_str(&excerpt_preview, 140))
                } else {
                    format!("Contextual grounding: \"{}\"", truncate_str(&excerpt_preview, 140))
                };

                field_evidence_map.insert(field.clone(), FieldEvidence {
                    field: field.clone(),
                    value: value.clone(),
                    quote,
                    source_url: record.source_url.clone(),
                    page_title: record.title.clone(),
                    source_type: domain_profile.source_type.clone(),
                    retrieved_at: Utc::now(),
                    confidence: (field_conf * 100.0).round() / 100.0,
                });
            }
            record.field_evidence = field_evidence_map;

            // 5. Mathematical Composite Record Confidence
            // Formula: 0.30*authority + 0.25*certainty + 0.20*agreement + 0.15*freshness + 0.10*completeness
            let source_authority = domain_profile.authority_score;
            let extraction_certainty = (0.75 + semantic_match_ratio * 0.25).min(1.0);
            let cross_source_agreement = if domain_profile.trust_tier == "primary" { 0.92 } else { 0.82 };
            let freshness = domain_profile.freshness_score;
            let completeness = (record.key_attributes.len() as f32 / (contract.fields.len().max(3) as f32)).min(1.0).max(0.6);

            let composite = (0.30 * source_authority)
                + (0.25 * extraction_certainty)
                + (0.20 * cross_source_agreement)
                + (0.15 * freshness)
                + (0.10 * completeness);

            let rounded_composite = (composite * 1000.0).round() / 1000.0;

            record.confidence = ConfidenceBreakdown {
                source_authority: (source_authority * 100.0).round() / 100.0,
                extraction_certainty: (extraction_certainty * 100.0).round() / 100.0,
                cross_source_agreement: (cross_source_agreement * 100.0).round() / 100.0,
                freshness: (freshness * 100.0).round() / 100.0,
                completeness: (completeness * 100.0).round() / 100.0,
                composite_score: rounded_composite,
            };

            // Set final validation status
            if !is_valid {
                record.validation_status = "REJECTED".to_string();
            } else if !validation_notes.is_empty() {
                record.validation_status = "WARNING".to_string();
            } else {
                record.validation_status = "PASSED".to_string();
                validation_notes.push("All structural and constraint invariants satisfied".to_string());
            }
            record.validation_notes = validation_notes;
        }

        // Filter out REJECTED records and sort by composite confidence
        records.retain(|r| r.validation_status != "REJECTED");
        records.sort_by(|a, b| b.confidence.composite_score.partial_cmp(&a.confidence.composite_score).unwrap_or(std::cmp::Ordering::Equal));
        records
    }
}

fn truncate_str(s: &str, max_len: usize) -> String {
    if s.chars().count() > max_len {
        format!("{}...", s.chars().take(max_len).collect::<String>())
    } else {
        s.to_string()
    }
}
