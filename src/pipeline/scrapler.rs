use crate::models::SearchResultItem;
use reqwest::Client;
use std::time::Duration;
use tracing::info;

pub struct LiveScraper;

impl LiveScraper {
    pub async fn scrape_and_verify(
        items: Vec<SearchResultItem>,
        max_to_scrape: usize,
    ) -> Vec<SearchResultItem> {
        let client = Client::builder()
            .timeout(Duration::from_millis(3500))
            .user_agent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
            .redirect(reqwest::redirect::Policy::limited(5))
            .build()
            .unwrap_or_default();

        let mut tasks = Vec::new();

        for (idx, mut item) in items.into_iter().enumerate() {
            let client_clone = client.clone();
            let should_deep_scrape = idx < max_to_scrape;

            tasks.push(tokio::spawn(async move {
                if !item.url.starts_with("http") {
                    return None;
                }

                // Verify site availability (strictly prevent 404s) and scrape live body
                match client_clone.get(&item.url).send().await {
                    Ok(resp) => {
                        let status = resp.status();
                        // Reject dead links (404, 410, 5xx)
                        if status == reqwest::StatusCode::NOT_FOUND
                            || status == reqwest::StatusCode::GONE
                            || status.is_server_error()
                        {
                            return None;
                        }

                        item.is_live = true;

                        if should_deep_scrape && status.is_success() {
                            if let Ok(html) = resp.text().await {
                                // 1. Adaptive Extraction: Check for JSON-LD structured data first
                                item.jsonld_data = extract_jsonld(&html);

                                // 2. Extract meaningful clean paragraph text chunks for RAG
                                let extracted_text = extract_meaningful_content(&html);
                                if extracted_text.len() > 60 {
                                    item.scraped_content = Some(extracted_text.clone());
                                    item.snippet = format!(
                                        "{}. Live Page Excerpt: {}",
                                        item.snippet.trim_end_matches('.'),
                                        extracted_text
                                    );
                                    item.relevance_score = (item.relevance_score + 0.15).min(1.0);
                                }
                            }
                        }

                        Some(item)
                    }
                    Err(_) => {
                        // Drop failed connections to prevent dead links
                        if item.source_engine.contains("Wikipedia") {
                            item.is_live = true;
                            Some(item)
                        } else {
                            None
                        }
                    }
                }
            }));
        }

        let mut verified = Vec::new();
        for t in tasks {
            if let Ok(Some(item)) = t.await {
                verified.push(item);
            }
        }

        info!("Adaptive Scraper verified {} live sources (404s dropped)", verified.len());
        verified
    }
}

fn extract_jsonld(html: &str) -> Option<serde_json::Value> {
    let re = regex::Regex::new(r#"(?is)<script[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script>"#).ok()?;
    for cap in re.captures_iter(html) {
        let raw = cap.get(1)?.as_str().trim();
        if let Ok(val) = serde_json::from_str::<serde_json::Value>(raw) {
            return Some(val);
        }
    }
    None
}

fn extract_meaningful_content(html: &str) -> String {
    // Strip scripts and styles
    let script_re = regex::Regex::new(r"(?is)<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<noscript[^>]*>.*?</noscript>|<header[^>]*>.*?</header>|<footer[^>]*>.*?</footer").unwrap();
    let cleaned = script_re.replace_all(html, " ");

    // Extract text from headings, paragraphs, and lists without backreferences
    let p_re = regex::Regex::new(r"(?is)<(p|li|h1|h2|h3)[^>]*>(.*?)</(?:p|li|h1|h2|h3)>").unwrap();
    let tag_re = regex::Regex::new(r"<[^>]*>|&nbsp;|&amp;|&quot;|&#39;").unwrap();
    let ws_re = regex::Regex::new(r"\s+").unwrap();

    let mut text_chunks = Vec::new();
    for cap in p_re.captures_iter(&cleaned) {
        let raw = tag_re.replace_all(&cap[2], " ");
        let normalized = ws_re.replace_all(&raw, " ").trim().to_string();
        if normalized.len() > 30 
            && !normalized.to_lowercase().contains("cookie") 
            && !normalized.to_lowercase().contains("privacy policy")
            && !normalized.to_lowercase().contains("terms of service")
            && !normalized.to_lowercase().contains("all rights reserved")
        {
            text_chunks.push(normalized);
            if text_chunks.len() >= 5 {
                break;
            }
        }
    }

    let joined = text_chunks.join(" ");
    let char_count = joined.chars().count();
    if char_count > 300 {
        joined.chars().take(300).collect::<String>()
    } else {
        joined
    }
}
