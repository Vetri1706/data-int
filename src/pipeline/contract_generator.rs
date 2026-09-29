use crate::config::AppConfig;
use crate::models::DataContract;
use reqwest::Client;
use serde_json::json;
use std::collections::HashMap;
use std::time::Duration;
use tracing::info;

pub struct ContractGeneratorStage;

impl ContractGeneratorStage {
    pub async fn generate(
        prompt: &str,
        category: &str,
        config: &AppConfig,
    ) -> DataContract {
        if let Some(ref api_key) = config.groq_api_key {
            if let Ok(contract) = Self::generate_via_llm(prompt, category, api_key).await {
                return contract;
            }
        }

        Self::generate_heuristic(prompt, category)
    }

    async fn generate_via_llm(
        prompt: &str,
        category: &str,
        api_key: &str,
    ) -> Result<DataContract, Box<dyn std::error::Error + Send + Sync>> {
        let client = Client::builder()
            .timeout(Duration::from_millis(3500))
            .build()?;

        let sys_prompt = r#"You are a Data Requirement Contract compiler. Given a user query, compile it into an executable JSON contract defining what constitutes a valid, structured data record.
Return ONLY valid JSON matching this schema:
{
  "entity": "e.g. job_opening, hospitality_property, b2b_lead, software_competitor, or product",
  "fields": {
    "field_name": "data_type (string, currency, date, url, or number)"
  },
  "constraints": [
    "e.g. location ~= Bangalore",
    "e.g. role related_to Rust"
  ],
  "freshness": "e.g. 7 days or current",
  "target_count": 25,
  "preferred_sources": ["e.g. company_career_pages", "e.g. verified_directories"],
  "critical_fields": ["field1", "field2"]
}"#;

        let body = json!({
            "model": "openai/gpt-oss-120b",
            "messages": [
                { "role": "system", "content": sys_prompt },
                { "role": "user", "content": format!("Category: {}\nUser Prompt: {}", category, prompt) }
            ],
            "response_format": { "type": "json_object" },
            "temperature": 0.1
        });

        let res = client
            .post("https://api.groq.com/openai/v1/chat/completions")
            .header("Authorization", format!("Bearer {}", api_key))
            .json(&body)
            .send()
            .await?;

        let res_json: serde_json::Value = res.json().await?;
        let text = res_json["choices"][0]["message"]["content"]
            .as_str()
            .unwrap_or("{}");

        if let Ok(contract) = serde_json::from_str::<DataContract>(text) {
            info!("Compiled dynamic DataContract via LLM for entity: {}", contract.entity);
            return Ok(contract);
        }

        Err("Failed to parse DataContract JSON".into())
    }

    fn generate_heuristic(prompt: &str, category: &str) -> DataContract {
        let p_lower = prompt.to_lowercase();
        let mut fields = HashMap::new();
        let mut constraints = Vec::new();
        let mut critical_fields = Vec::new();
        let entity;
        let mut preferred_sources = Vec::new();

        if p_lower.contains("job") || p_lower.contains("developer") || p_lower.contains("hiring") || p_lower.contains("intern") {
            entity = "job_opening".to_string();
            fields.insert("company".to_string(), "string".to_string());
            fields.insert("role".to_string(), "string".to_string());
            fields.insert("location".to_string(), "string".to_string());
            fields.insert("salary_or_stipend".to_string(), "currency".to_string());
            fields.insert("apply_url".to_string(), "url".to_string());
            critical_fields.extend(vec!["company".to_string(), "role".to_string(), "apply_url".to_string()]);
            preferred_sources.extend(vec!["company_career_pages".to_string(), "job_boards".to_string()]);
            
            if p_lower.contains("bangalore") || p_lower.contains("bengaluru") {
                constraints.push("location ~= Bangalore".to_string());
            }
            if p_lower.contains("remote") {
                constraints.push("workmode contains Remote".to_string());
            }
        } else if p_lower.contains("resort") || p_lower.contains("hotel") || p_lower.contains("stay") {
            entity = "hospitality_property".to_string();
            fields.insert("property_name".to_string(), "string".to_string());
            fields.insert("location".to_string(), "string".to_string());
            fields.insert("pricing".to_string(), "currency".to_string());
            fields.insert("booking_channel".to_string(), "url".to_string());
            fields.insert("amenities".to_string(), "string".to_string());
            critical_fields.extend(vec!["property_name".to_string(), "booking_channel".to_string()]);
            preferred_sources.extend(vec!["official_hotel_sites".to_string(), "verified_booking_portals".to_string()]);
            
            if p_lower.contains("ooty") {
                constraints.push("location ~= Ooty".to_string());
            }
        } else {
            entity = format!("{}_record", category);
            fields.insert("name_or_title".to_string(), "string".to_string());
            fields.insert("primary_url".to_string(), "url".to_string());
            fields.insert("description".to_string(), "string".to_string());
            fields.insert("source_domain".to_string(), "string".to_string());
            critical_fields.extend(vec!["name_or_title".to_string(), "primary_url".to_string()]);
            preferred_sources.extend(vec!["primary_industry_sources".to_string(), "authoritative_directories".to_string()]);
        }

        DataContract {
            entity,
            fields,
            constraints,
            freshness: "recent".to_string(),
            target_count: 20,
            preferred_sources,
            critical_fields,
        }
    }
}
