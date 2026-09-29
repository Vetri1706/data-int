pub mod contract_generator;
pub mod entity_resolver;
pub mod scrapler;
pub mod search_provider;
pub mod source_registry;
pub mod stage1_classifier;
pub mod stage2_rewriter;
pub mod stage3_retriever;
pub mod stage4_reranker;
pub mod stage5_synthesizer;
pub mod validator_engine;

use chrono::Utc;
use std::time::Instant;
use uuid::Uuid;

use crate::config::AppConfig;
use crate::models::{
    GroundingMetadata, GroundingRequest, GroundingResponse, StageMetric, WorkflowStats,
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
                data_contract: None,
                workflow_stats: None,
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

        // Stage 2: Data Requirement Contract Compilation
        let s2_start = Instant::now();
        let contract = contract_generator::ContractGeneratorStage::generate(
            &req.prompt,
            &intent.category,
            config,
        ).await;
        stages.push(StageMetric {
            stage_number: 2,
            stage_name: "Data Requirement Contract Compiler".to_string(),
            duration_ms: s2_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!(
                "Compiled schema for entity '{}' with {} critical fields & {} constraints",
                contract.entity, contract.critical_fields.len(), contract.constraints.len()
            ),
        });

        // Stage 3: Query Rewriting & Multi-Angle Expansion
        let s3_start = Instant::now();
        let expansion = stage2_rewriter::QueryRewriterStage::rewrite(&req.prompt, &intent.category).await;
        stages.push(StageMetric {
            stage_number: 3,
            stage_name: "Query Rewriting & Multi-Hypothesis Expansion".to_string(),
            duration_ms: s3_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Generated {} search-optimized queries", expansion.rewritten_queries.len()),
        });

        // Stage 4: Multi-Source Web Retrieval & Adaptive RAG Extraction
        let s4_start = Instant::now();
        let raw_results = stage3_retriever::RetrieverStage::retrieve(
            &expansion.rewritten_queries,
            config,
            max_sources,
        ).await;
        
        let domains_discovered = raw_results.len();
        stages.push(StageMetric {
            stage_number: 4,
            stage_name: "Multi-Source Web Retrieval & Adaptive Scraping".to_string(),
            duration_ms: s4_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Discovered & verified {} live 200 OK sources (404 dead links purged)", raw_results.len()),
        });

        // Stage 5: Deduplication, Reranking & Context Blending
        let s5_start = Instant::now();
        let blended = stage4_reranker::RerankerStage::rerank_and_blend(
            raw_results,
            &req.prompt,
            max_sources,
        );
        stages.push(StageMetric {
            stage_number: 5,
            stage_name: "Source Reranking & Context Blending".to_string(),
            duration_ms: s5_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Ranked top {} authoritative sources for context injection", blended.citations.len()),
        });

        // Stage 6: Cross-Referenced LLM Synthesis & Attribute Extraction
        let s6_start = Instant::now();
        let synthesis = stage5_synthesizer::SynthesizerStage::synthesize(
            &req.prompt,
            &blended.context_block,
            &blended.citations,
            &intent.category,
            config,
        ).await;
        let records_extracted = synthesis.dataset.len();
        stages.push(StageMetric {
            stage_number: 6,
            stage_name: "LLM Grounded Synthesis & Attribute Extraction".to_string(),
            duration_ms: s6_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Synthesized report with inline citations and extracted {} candidate records", synthesis.dataset.len()),
        });

        // Stage 7: Validation Engine & Field Evidence Provenance
        let s7_start = Instant::now();
        let registry = source_registry::SourceRegistry::new();
        let validated_records = validator_engine::ValidatorEngine::validate_and_score(
            synthesis.dataset,
            &contract,
            &registry,
            &req.prompt,
        );
        let records_validated = validated_records.len();
        stages.push(StageMetric {
            stage_number: 7,
            stage_name: "Constraint Validation & Field Evidence Scoring".to_string(),
            duration_ms: s7_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Evaluated field-level evidence and computed multi-factor confidence for {} records", validated_records.len()),
        });

        // Stage 8: Entity Resolution & Deduplication
        let s8_start = Instant::now();
        let final_records = entity_resolver::EntityResolver::resolve_and_deduplicate(validated_records);
        let records_final = final_records.len();
        stages.push(StageMetric {
            stage_number: 8,
            stage_name: "Entity Resolution & Provenance Graph Merging".to_string(),
            duration_ms: s8_start.elapsed().as_millis() as u64,
            status: "COMPLETED".to_string(),
            description: format!("Consolidated {} canonical entities with corroborated cross-source evidence", records_final),
        });

        let workflow_id = format!("WF-{}", &Uuid::new_v4().to_string()[..8]);
        let dag_summary = format!(
            "{}: Search → {} discovered → {} collected → {} extracted → {} validated → {} final canonical records",
            workflow_id, domains_discovered, blended.citations.len(), records_extracted, records_validated, records_final
        );

        let workflow_stats = WorkflowStats {
            workflow_id: workflow_id.clone(),
            state: "COMPLETED".to_string(),
            domains_discovered,
            domains_accepted: blended.citations.len(),
            pages_collected: blended.citations.len(),
            records_extracted,
            records_validated,
            records_final,
            dag_summary,
        };

        GroundingResponse {
            id: Uuid::new_v4().to_string(),
            timestamp: Utc::now(),
            prompt: req.prompt,
            intent: intent.clone(),
            data_contract: Some(contract),
            workflow_stats: Some(workflow_stats),
            answer_markdown: synthesis.answer_markdown,
            grounding_metadata: GroundingMetadata {
                search_queries: expansion.rewritten_queries,
                sources: blended.citations,
                grounding_threshold: threshold,
                intent_score: intent.confidence_score,
                triggered_grounding: true,
            },
            dataset: final_records,
            pipeline_stages: stages,
            total_latency_ms: total_start.elapsed().as_millis() as u64,
        }
    }
}
