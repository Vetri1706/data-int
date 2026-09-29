use crate::models::QueryExpansion;
use regex::Regex;

pub struct QueryRewriterStage;

impl QueryRewriterStage {
    pub async fn rewrite(prompt: &str, category: &str) -> QueryExpansion {
        let p_clean = prompt.trim();

        // 1. Remove conversational filler phrases
        let filler_re = Regex::new(
            r"(?i)^(hey|hello|hi|please|can you|could you|i need to|i want to|find me|find|search for|look up|give me|what are|tell me about|show me|list|get)\s+"
        ).unwrap();
        let cleaned = filler_re.replace_all(p_clean, "").to_string();

        // 2. Identify key location if present
        let loc_re = Regex::new(r"(?i)\b(?:in|near|at|around)\s+([a-zA-Z]+)\b").unwrap();
        let location = loc_re.captures(&cleaned).map(|c| c[1].to_lowercase());

        // 3. Remove common stop prepositions and fluff
        let noise_re = Regex::new(r"(?i)\b(with|for|the|a|an|some|any|all|of|about|direct|deals|booking)\b").unwrap();
        let stripped = noise_re.replace_all(&cleaned, " ");
        let core_words: Vec<&str> = stripped.split_whitespace().collect();

        let mut rewritten_queries = Vec::new();

        // Query 1: Core entity + location (e.g., "luxury resorts ooty" or "rust developer bangalore")
        if let Some(ref loc) = location {
            let entity_words: Vec<&str> = core_words.iter()
                .filter(|&&w| !w.eq_ignore_ascii_case(loc) && !["in", "near", "at"].contains(&w.to_lowercase().as_str()))
                .take(3)
                .cloned()
                .collect();
            if !entity_words.is_empty() {
                rewritten_queries.push(format!("{} {}", entity_words.join(" "), loc));
            }
        }

        // Query 2: Cleaned keywords
        let pure_keywords = core_words.iter().take(5).cloned().collect::<Vec<_>>().join(" ");
        if !pure_keywords.is_empty() {
            rewritten_queries.push(pure_keywords);
        }

        // Query 3: Full cleaned query
        rewritten_queries.push(cleaned);

        rewritten_queries.dedup();

        QueryExpansion {
            original_prompt: prompt.to_string(),
            rewritten_queries,
            target_intent: category.to_string(),
        }
    }
}
