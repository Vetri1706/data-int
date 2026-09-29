use crate::models::{GroundingResponse, TaskHistorySummary};
use std::collections::VecDeque;
use std::sync::Arc;
use tokio::sync::RwLock;

#[derive(Clone)]
pub struct TaskStore {
    history: Arc<RwLock<VecDeque<GroundingResponse>>>,
    max_items: usize,
}

impl TaskStore {
    pub fn new(max_items: usize) -> Self {
        Self {
            history: Arc::new(RwLock::new(VecDeque::with_capacity(max_items))),
            max_items,
        }
    }

    pub async fn add_task(&self, resp: GroundingResponse) {
        let mut store = self.history.write().await;
        if store.len() >= self.max_items {
            store.pop_back();
        }
        store.push_front(resp);
    }

    pub async fn get_history(&self) -> Vec<TaskHistorySummary> {
        let store = self.history.read().await;
        store
            .iter()
            .map(|t| TaskHistorySummary {
                id: t.id.clone(),
                timestamp: t.timestamp,
                prompt: t.prompt.clone(),
                category: t.intent.category.clone(),
                records_count: t.dataset.len(),
                sources_count: t.grounding_metadata.sources.len(),
                total_latency_ms: t.total_latency_ms,
                triggered_grounding: t.grounding_metadata.triggered_grounding,
            })
            .collect()
    }

    pub async fn get_task_by_id(&self, id: &str) -> Option<GroundingResponse> {
        let store = self.history.read().await;
        store.iter().find(|t| t.id == id).cloned()
    }
}
