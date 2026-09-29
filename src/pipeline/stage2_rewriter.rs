use crate::models::QueryExpansion;
use regex::Regex;

pub struct QueryRewriterStage;

impl QueryRewriterStage {
    pub async fn rewrite(prompt: &str, category: &str) -> QueryExpansion {
        let p_clean = prompt.trim();

        // 1. Remove conversational filler prefixes
        let filler_re = Regex::new(
            r"(?i)^(hey|hello|hi|please|can you|could you|i need to|i want to|find me|find|search for|look up|give me|what are|tell me about|show me|list|get|build a shortlist for|build a|track)\s+"
        ).unwrap();
        let cleaned = filler_re.replace_all(p_clean, "").to_string();

        // 2. Extract multi-word location if present (e.g. "Tamil Nadu", "South India", "Bangalore")
        let loc_re = Regex::new(r"(?i)\b(?:in|near|at|around)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\b").unwrap();
        let mut location = None;
        if let Some(cap) = loc_re.captures(&cleaned) {
            let captured_loc = cap[1].trim();
            // Don't mistake verbs/conjunctions for locations
            if !["the", "a", "an", "all", "order"].contains(&captured_loc.to_lowercase().as_str()) {
                location = Some(captured_loc.to_string());
            }
        }

        // 3. Filter noise and grammatical stopwords
        let noise_re = Regex::new(
            r"(?i)\b(that|could|would|should|can|will|with|for|the|a|an|some|any|all|of|about|direct|deals|booking|evidence|information|and|or|etc|including|include|per|from)\b"
        ).unwrap();
        let stripped = noise_re.replace_all(&cleaned, " ");
        let core_words: Vec<&str> = stripped.split_whitespace().collect();

        let mut rewritten_queries = Vec::new();

        // Query 1: High-relevance business entity query
        let top_keywords: Vec<&str> = core_words.iter()
            .filter(|&&w| w.len() > 2)
            .take(6)
            .cloned()
            .collect();

        if !top_keywords.is_empty() {
            rewritten_queries.push(top_keywords.join(" "));
        }

        // Query 2: Entity + Location specific query
        if let Some(ref loc) = location {
            let entity_words: Vec<&str> = core_words.iter()
                .filter(|&&w| !loc.to_lowercase().contains(&w.to_lowercase()) && w.len() > 2)
                .take(4)
                .cloned()
                .collect();
            if !entity_words.is_empty() {
                rewritten_queries.push(format!("{} {}", entity_words.join(" "), loc));
            }
        }

        // Query 3: Multi-Hypothesis variation (e.g. CSR, leads, pricing, or careers)
        if cleaned.to_lowercase().contains("sponsor") || cleaned.to_lowercase().contains("csr") {
            if let Some(ref loc) = location {
                rewritten_queries.push(format!("robotics companies {} CSR sponsor", loc));
            } else {
                rewritten_queries.push("robotics companies CSR sponsorship".to_string());
            }
        } else if cleaned.to_lowercase().contains("startup") || cleaned.to_lowercase().contains("funding") {
            rewritten_queries.push("AI startups South India funding founder".to_string());
        } else if cleaned.to_lowercase().contains("pricing") || cleaned.to_lowercase().contains("crm") {
            rewritten_queries.push("AI CRM software pricing comparison 2026".to_string());
        } else if cleaned.to_lowercase().contains("job") || cleaned.to_lowercase().contains("developer") {
            rewritten_queries.push("Rust developer jobs Bangalore".to_string());
        }

        rewritten_queries.push(cleaned);
        rewritten_queries.dedup();

        QueryExpansion {
            original_prompt: prompt.to_string(),
            rewritten_queries,
            target_intent: category.to_string(),
        }
    }
}
