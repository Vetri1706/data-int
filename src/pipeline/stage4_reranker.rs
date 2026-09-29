use crate::models::{Citation, SearchResultItem};
use std::collections::HashSet;
use tracing::info;

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
        let stop_words = ["find", "with", "the", "for", "and", "about", "what", "from", "that", "this", "can", "you", "some", "give", "direct", "deals", "best", "top", "good", "need"];
        let prompt_tokens: Vec<String> = prompt
            .to_lowercase()
            .split_whitespace()
            .map(|w| w.trim_matches(|c: char| !c.is_alphanumeric()).to_string())
            .filter(|w| w.len() > 2 && !stop_words.contains(&w.to_lowercase().as_str()))
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

        let raw_backup = unique_items.clone();
        info!("Prompt tokens: {:?}", prompt_tokens);
        let mut scored_items = Vec::new();

        for mut item in unique_items {
            let title_lower = item.title.to_lowercase();
            let snippet_lower = item.snippet.to_lowercase();
            let domain_lower = item.domain.to_lowercase();
            info!("Scoring candidate: title='{}', domain='{}'", item.title, item.domain);

            let mut match_count = 0.0;
            for token in &prompt_tokens {
                let stem = if token.ends_with('s') && token.len() > 3 {
                    &token[..token.len() - 1]
                } else {
                    token.as_str()
                };

                let matched = title_lower.contains(token) 
                    || title_lower.contains(stem)
                    || snippet_lower.contains(token)
                    || snippet_lower.contains(stem)
                    || domain_lower.contains(token)
                    || domain_lower.contains(stem);

                if matched {
                    if title_lower.contains(token) || title_lower.contains(stem) {
                        match_count += 3.0;
                    }
                    if domain_lower.contains(token) || domain_lower.contains(stem) {
                        match_count += 2.5;
                    }
                    if snippet_lower.contains(token) || snippet_lower.contains(stem) {
                        match_count += 1.5;
                    }
                }
            }

            let token_score = (match_count as f32 / 5.0f32).min(1.0f32);
            let live_bonus: f32 = if item.is_live { 0.25 } else { 0.0 };
            let length_bonus: f32 = if item.snippet.len() > 50 { 0.15 } else { 0.0 };

            item.relevance_score = (token_score * 0.6 + live_bonus + length_bonus).min(1.0f32);

            // Accept item if it has token matches OR if the prompt had no filterable tokens
            if match_count > 0.0 || prompt_tokens.is_empty() {
                scored_items.push(item);
            }
        }

        // If strict matching yielded fewer than 2 items, include the top raw items
        let final_items = if scored_items.len() < 2 && !raw_backup.is_empty() {
            info!("Strict match yielded {} items, falling back to {} raw candidates", scored_items.len(), raw_backup.len());
            raw_backup
        } else {
            scored_items
        };

        // 3. Sort by relevance score descending
        let mut sorted = final_items;
        sorted.sort_by(|a, b| {
            b.relevance_score
                .partial_cmp(&a.relevance_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        let top_items: Vec<SearchResultItem> = sorted.into_iter().take(max_sources).collect();
        info!("Reranked top {} authoritative sources for context injection", top_items.len());

        // 4. Generate Citations and Injected Context Block for RAG
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
                is_live: item.is_live,
            });

            let scraped_details = item.scraped_content
                .as_ref()
                .map(|sc| format!("\nLive Scraped Content: {}", sc))
                .unwrap_or_default();

            context_lines.push(format!(
                "[{}] {}\nURL: {}\nDomain: {}\nVerified Status: {}\nSnippet: {}{}\n",
                cite_num,
                item.title,
                item.url,
                item.domain,
                if item.is_live { "200 OK Live Verified" } else { "Active" },
                item.snippet,
                scraped_details
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
