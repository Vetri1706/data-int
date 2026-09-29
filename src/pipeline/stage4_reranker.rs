use crate::models::{Citation, SearchResultItem};
use std::collections::HashSet;

pub struct RerankerStage;

#[allow(dead_code)]
pub struct BlendedContext {
    pub ranked_results: Vec<SearchResultItem>,
    pub citations: Vec<Citation>,
    pub context_block: String,
}

impl RerankerStage {
    pub fn rerank_and_blend(
        mut items: Vec<SearchResultItem>,
        prompt: &str,
        max_sources: usize,
    ) -> BlendedContext {
        let prompt_tokens: Vec<String> = prompt
            .to_lowercase()
            .split_whitespace()
            .filter(|w| w.len() > 2)
            .map(|s| s.to_string())
            .collect();

        // 1. Deduplicate by normalized URL
        let mut seen_urls = HashSet::new();
        let mut unique_items = Vec::new();

        for item in items.drain(..) {
            let norm_url = item.url.trim_end_matches('/').to_lowercase();
            if seen_urls.insert(norm_url) && !item.title.is_empty() {
                unique_items.push(item);
            }
        }

        // 2. Score relevance based on token matching, snippet length, and domain authority
        for item in &mut unique_items {
            let title_lower = item.title.to_lowercase();
            let snippet_lower = item.snippet.to_lowercase();
            let domain_lower = item.domain.to_lowercase();

            let mut match_count = 0.0;
            for token in &prompt_tokens {
                if title_lower.contains(token) {
                    match_count += 2.0; // title match counts double
                }
                if snippet_lower.contains(token) {
                    match_count += 1.0;
                }
                if domain_lower.contains(token) {
                    match_count += 1.5;
                }
            }

            let token_score = if !prompt_tokens.is_empty() {
                match_count / (prompt_tokens.len() as f32 * 3.0)
            } else {
                0.5
            };

            // Bonus for healthy snippet length (not stub, not empty)
            let length_bonus = if item.snippet.len() > 60 { 0.15 } else { 0.0 };

            item.relevance_score = (token_score * 0.7 + length_bonus + 0.15).min(1.0);
        }

        // 3. Sort by relevance score descending
        unique_items.sort_by(|a, b| b.relevance_score.partial_cmp(&a.relevance_score).unwrap_or(std::cmp::Ordering::Equal));

        let top_items: Vec<SearchResultItem> = unique_items.into_iter().take(max_sources).collect();

        // 4. Generate Citations and Injected Context Block
        let mut citations = Vec::new();
        let mut context_lines = Vec::new();

        for (idx, item) in top_items.iter().enumerate() {
            let cite_num = idx + 1;
            citations.push(Citation {
                index: cite_num,
                url: item.url.clone(),
                title: item.title.clone(),
                domain: item.domain.clone(),
                snippet: item.snippet.clone(),
            });

            context_lines.push(format!(
                "[{}] {}\nURL: {}\nDomain: {}\nSnippet: {}\n",
                cite_num, item.title, item.url, item.domain, item.snippet
            ));
        }

        let context_block = context_lines.join("\n---\n");

        BlendedContext {
            ranked_results: top_items,
            citations,
            context_block,
        }
    }
}
