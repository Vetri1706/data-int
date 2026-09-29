use crate::models::QueryExpansion;
use regex::Regex;

pub struct QueryRewriterStage;

impl QueryRewriterStage {
    pub async fn rewrite(prompt: &str, category: &str) -> QueryExpansion {
        // Strip common conversational preamble and filler phrases
        let filler_re = Regex::new(r"(?i)^(hey|hello|hi|please|can you|could you|i need to|i want to|find me|search for|look up|give me|what are|tell me about)\s+").unwrap();
        let cleaned = filler_re.replace_all(prompt.trim(), "").to_string();

        let mut rewritten_queries = Vec::new();

        // 1. Primary search-optimized query: stripped of conversational noise
        let primary_query = cleaned.clone();
        rewritten_queries.push(primary_query.clone());

        // 2. Keyword & domain diversification queries based on category
        match category {
            "business_intelligence" => {
                rewritten_queries.push(format!("{} hiring careers openings", primary_query));
                rewritten_queries.push(format!("{} direct company listings", primary_query));
            }
            "commercial_procurement" => {
                rewritten_queries.push(format!("{} specifications price official", primary_query));
                rewritten_queries.push(format!("{} reviews compare best deals", primary_query));
            }
            _ => {
                rewritten_queries.push(format!("{} latest updates", primary_query));
                rewritten_queries.push(format!("{} verified facts official", primary_query));
            }
        }

        QueryExpansion {
            original_prompt: prompt.to_string(),
            rewritten_queries,
            target_intent: category.to_string(),
        }
    }
}
