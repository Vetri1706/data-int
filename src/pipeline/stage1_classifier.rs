use crate::models::IntentClassification;
use regex::Regex;

pub struct ClassifierStage;

impl ClassifierStage {
    pub async fn classify(prompt: &str, threshold: f32) -> IntentClassification {
        let p_lower = prompt.to_lowercase();
        let mut score: f32 = 0.25; // baseline
        let mut reasons = Vec::new();
        let mut category = "general_knowledge".to_string();
        let mut trigger_type = "offline_knowledge".to_string();

        // 1. Math / Pure coding / Theoretical prompts (decrease score)
        let math_code_pattern = Regex::new(r"^(what is \d+\s*[\+\-\*/]\s*\d+|write (a )?(python|rust|js|c\+\+|code|script)|solve for x|explain (recursion|gravity|quantum))").unwrap();
        if math_code_pattern.is_match(&p_lower) {
            score = 0.10;
            reasons.push("Prompt is a static computational, coding, or theoretical question");
            return IntentClassification {
                needs_search: false,
                confidence_score: score,
                reasoning: reasons.join("; "),
                category: "code_or_math".to_string(),
                trigger_type: "offline_computational".to_string(),
            };
        }

        // 2. Business data & Lead generation signals (high trigger)
        let business_pattern = Regex::new(r"\b(jobs?|hiring|openings?|careers?|salaries|salary|leads?|founders?|sponsors?|companies|startups|market share|competitors?|b2b)\b").unwrap();
        if business_pattern.is_match(&p_lower) {
            score += 0.50;
            category = "business_intelligence".to_string();
            trigger_type = "market_or_leads".to_string();
            reasons.push("Business intelligence or talent/lead acquisition intent detected");
        }

        // 3. Products, prices, shopping, real estate
        let commerce_pattern = Regex::new(r"\b(price|cost|buy|cheap|best|deal|discount|resorts?|hotels?|apartments?|flats?|rent|reviews?|specs)\b").unwrap();
        if commerce_pattern.is_match(&p_lower) {
            score += 0.45;
            category = "commercial_procurement".to_string();
            trigger_type = "pricing_and_availability".to_string();
            reasons.push("Real-time pricing, commercial inventory or product comparison required");
        }

        // 4. Temporal recency indicators
        let temporal_pattern = Regex::new(r"\b(latest|current|recent|today|yesterday|2024|2025|2026|new|updated|now|this week|this month)\b").unwrap();
        if temporal_pattern.is_match(&p_lower) {
            score += 0.35;
            trigger_type = "realtime_events".to_string();
            reasons.push("Explicit temporal recency marker demands live external retrieval");
        }

        // 5. Geographic / location specificity
        let geo_pattern = Regex::new(r"\b(in|near|at|around)\s+([a-z]+)\b").unwrap();
        if geo_pattern.is_match(&p_lower) {
            score += 0.20;
            reasons.push("Geographic grounding constraint detected");
        }

        // Clamp score between 0.0 and 1.0
        let final_score = score.min(1.0).max(0.0);
        let needs_search = final_score >= threshold;

        if reasons.is_empty() {
            reasons.push("Default evaluation based on conversational complexity");
        }

        IntentClassification {
            needs_search,
            confidence_score: final_score,
            reasoning: reasons.join("; "),
            category,
            trigger_type,
        }
    }
}
