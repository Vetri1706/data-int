pub mod stage1_classifier;
pub mod stage2_rewriter;
pub mod stage3_retriever;
pub mod stage4_reranker;
pub mod stage5_synthesizer;

use chrono::Utc;
use std::time::Instant;
use uuid::Uuid;

use crate::config::AppConfig;
use crate::models::{
    GroundingMetadata, GroundingRequest, GroundingResponse, StageMetric,
};

pub struct GroundingPipeline;

impl GroundingPipeline {
    pub async fn execute(req: GroundingRequest, config: &AppConfig) -> GroundingResponse {
        let total_start = Instant::now();
        let mut stages = Vec::new();
        let threshold = req.grounding_threshold.unwrap_or(config.default_grounding_threshold);
        let max_sources = req.max_sources.unwrap_or(8);

        // Stage 1: Intent Detection & Dynamic Thresholding
        let s1_start = Instant::now();
        let intent = stage1_classifier::ClassifierStage::classify(&req.prompt, threshold).await;
        stages.push(StageMetric {
            stage_number: 1,
            stage_name: "Intent Detection & Dynamic Thresholding".to_string(),
            duration_ms: s1_start.elapsed().as_millis() as u64,
            status: if intent.needs_search { "TRIGGERED".to_string() } else { "SKIPPED".to_string() },
            description: format!(
                "Confidence score: {:.2} (Threshold: {:.2}). {}",
                intent.confidence_score, threshold, intent.reasoning
            ),
        });

        // If threshold not met, return offline conversational response
        if !intent.needs_search {
            return GroundingResponse {
                id: Uuid::new_v4().to_string(),
                timestamp: Utc::now(),
                prompt: req.prompt.clone(),
                intent: intent.clone(),
                answer_markdown: format!(
                    "### Offline / Direct Answer\n\n\
                    Your query scored **{:.2}**, which is below the Search Grounding threshold of **{:.2}**.\n\
                    Live external retrieval was not triggered because this prompt can be solved directly from model training or computational reasoning.",
                    intent.confidence_score, threshold
                ),
                grounding_metadata: GroundingMetadata {
                    search_queries: Vec::new(),
                    sources: Vec::new(),
                    grounding_threshold: threshold,
                    intent_score: intent.confidence_score,
                    triggered_grounding: false,
                },
                dataset: Vec::new(),
                pipeline_stages: stages,
                total_latency_ms: total_start.elapsed().as_millis() as u64,
            };
        }

        // Stage 2: Query Rewriting & Expansion
        let s2_start = Instant::now();
        let expansion = stage2_rewriter::QueryRewriterStage::rewrite(&req.prompt, &intent.category).await;
        stages.push(StageMetric {
            stage_number: 2,
            stage_name: "Query Rewriting & Multi-Angle Expansion".to_string(),
            duration_ms: s2_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Generated {} search-optimized queries", expansion.rewritten_queries.len()),
        });

        // Stage 3: Retrieval (Multi-source Fetching)
        let s3_start = Instant::now();
        let raw_results = stage3_retriever::RetrieverStage::retrieve(
            &expansion.rewritten_queries,
            config,
            max_sources,
        ).await;
        stages.push(StageMetric {
            stage_number: 3,
            stage_name: "Multi-Source Web Retrieval".to_string(),
            duration_ms: s3_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Harvested {} candidate snippets from web indexes", raw_results.len()),
        });

        // Stage 4: Deduplication, Reranking & Context Blending
        let s4_start = Instant::now();
        let blended = stage4_reranker::RerankerStage::rerank_and_blend(
            raw_results,
            &req.prompt,
            max_sources,
        );
        stages.push(StageMetric {
            stage_number: 4,
            stage_name: "Deduplication, Reranking & Blending".to_string(),
            duration_ms: s4_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Filtered and ranked top {} authoritative sources", blended.citations.len()),
        });

        // Stage 5: Aggregation, Cross-Referencing & LLM Synthesis
        let s5_start = Instant::now();
        let synthesis = stage5_synthesizer::SynthesizerStage::synthesize(
            &req.prompt,
            &blended.context_block,
            &blended.citations,
            &intent.category,
            config,
        ).await;
        stages.push(StageMetric {
            stage_number: 5,
            stage_name: "Cross-Referencing & Synthesis with Inline Citations".to_string(),
            duration_ms: s5_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Synthesized report and mapped {} structured records", synthesis.dataset.len()),
        });

        GroundingResponse {
            id: Uuid::new_v4().to_string(),
            timestamp: Utc::now(),
            prompt: req.prompt,
            intent: intent.clone(),
            answer_markdown: synthesis.answer_markdown,
            grounding_metadata: GroundingMetadata {
                search_queries: expansion.rewritten_queries,
                sources: blended.citations,
                grounding_threshold: threshold,
                intent_score: intent.confidence_score,
                triggered_grounding: true,
            },
            dataset: synthesis.dataset,
            pipeline_stages: stages,
            total_latency_ms: total_start.elapsed().as_millis() as u64,
        }
    }
}
