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

        let sys_prompt = r#"You are an Enterprise Business Data Requirement Contract compiler.
Given a business question (e.g. startup leads, sponsorship procurement, competitor pricing, supplier shortlists, or hiring intel), compile it into an executable JSON contract defining what constitutes an auditable, business-ready data record.
Return ONLY valid JSON matching this schema:
{
  "entity": "e.g. b2b_sales_lead, sponsor_opportunity, job_opening, competitor_pricing, supplier_shortlist, or hospitality_property",
  "fields": {
    "field_name": "data_type (string, currency, date, url, or number)"
  },
  "constraints": [
    "e.g. location ~= South India",
    "e.g. funding_round in ['Seed', 'Series A']"
  ],
  "freshness": "e.g. 18 months, 7 days, or current",
  "target_count": 25,
  "preferred_sources": ["e.g. official_company_sites", "e.g. verified_directories", "e.g. regulatory_filings"],
  "critical_fields": ["field1", "field2"]
}"#;

        let body = json!({
            "model": "openai/gpt-oss-120b",
            "messages": [
                { "role": "system", "content": sys_prompt },
                { "role": "user", "content": format!("Category: {}\nBusiness Requirement: {}", category, prompt) }
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
            info!("Compiled enterprise DataContract for business entity: {}", contract.entity);
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
        let mut freshness = "recent".to_string();

        if p_lower.contains("startup") || p_lower.contains("lead") || p_lower.contains("funding") {
            // Archetype 1: B2B Sales Leads & Venture Intelligence
            entity = "b2b_sales_lead".to_string();
            fields.insert("company_name".to_string(), "string".to_string());
            fields.insert("founder".to_string(), "string".to_string());
            fields.insert("location".to_string(), "string".to_string());
            fields.insert("funding_round".to_string(), "string".to_string());
            fields.insert("website".to_string(), "url".to_string());
            fields.insert("market_segment".to_string(), "string".to_string());
            critical_fields.extend(vec!["company_name".to_string(), "website".to_string(), "location".to_string()]);
            preferred_sources.extend(vec!["official_company_websites".to_string(), "crunchbase_or_venture_indexes".to_string()]);
            freshness = "18 months".to_string();
            
            if p_lower.contains("south india") || p_lower.contains("bangalore") || p_lower.contains("chennai") {
                constraints.push("location in ['Bangalore', 'Chennai', 'Hyderabad', 'South India']".to_string());
            }
        } else if p_lower.contains("sponsor") || p_lower.contains("hackathon") || p_lower.contains("csr") {
            // Archetype 2: Sponsorship Procurement & Corporate Partnerships
            entity = "sponsor_opportunity".to_string();
            fields.insert("company_name".to_string(), "string".to_string());
            fields.insert("csr_or_sponsorship_focus".to_string(), "string".to_string());
            fields.insert("contact_channel".to_string(), "url".to_string());
            fields.insert("relevance_evidence".to_string(), "string".to_string());
            fields.insert("website".to_string(), "url".to_string());
            critical_fields.extend(vec!["company_name".to_string(), "website".to_string(), "relevance_evidence".to_string()]);
            preferred_sources.extend(vec!["official_corporate_sites".to_string(), "csr_program_disclosures".to_string()]);
            
            if p_lower.contains("robotics") {
                constraints.push("relevance related_to Robotics or STEM".to_string());
            }
            if p_lower.contains("tamil nadu") || p_lower.contains("chennai") {
                constraints.push("location ~= Tamil Nadu".to_string());
            }
        } else if p_lower.contains("pricing") || p_lower.contains("crm") || p_lower.contains("saas") || p_lower.contains("competitor") {
            // Archetype 3: Competitor Pricing & Market Intelligence
            entity = "competitor_pricing".to_string();
            fields.insert("product_name".to_string(), "string".to_string());
            fields.insert("vendor".to_string(), "string".to_string());
            fields.insert("pricing_tiers".to_string(), "currency".to_string());
            fields.insert("key_features".to_string(), "string".to_string());
            fields.insert("official_pricing_url".to_string(), "url".to_string());
            critical_fields.extend(vec!["product_name".to_string(), "pricing_tiers".to_string(), "official_pricing_url".to_string()]);
            preferred_sources.extend(vec!["official_vendor_pricing_pages".to_string(), "verified_saas_directories".to_string()]);
            freshness = "current (2026)".to_string();
        } else if p_lower.contains("supplier") || p_lower.contains("distributor") || p_lower.contains("procurement") {
            // Archetype 4: Supplier Shortlist & Procurement Intelligence
            entity = "supplier_shortlist".to_string();
            fields.insert("supplier_name".to_string(), "string".to_string());
            fields.insert("product_category".to_string(), "string".to_string());
            fields.insert("location".to_string(), "string".to_string());
            fields.insert("pricing_availability".to_string(), "string".to_string());
            fields.insert("catalog_url".to_string(), "url".to_string());
            critical_fields.extend(vec!["supplier_name".to_string(), "catalog_url".to_string()]);
            preferred_sources.extend(vec!["manufacturer_catalogs".to_string(), "industrial_distributor_indexes".to_string()]);
        } else if p_lower.contains("job") || p_lower.contains("developer") || p_lower.contains("hiring") || p_lower.contains("intern") {
            // Archetype 5: Talent & Hiring Intelligence
            entity = "job_opening".to_string();
            fields.insert("company_name".to_string(), "string".to_string());
            fields.insert("role".to_string(), "string".to_string());
            fields.insert("location".to_string(), "string".to_string());
            fields.insert("salary_or_stipend".to_string(), "currency".to_string());
            fields.insert("apply_url".to_string(), "url".to_string());
            critical_fields.extend(vec!["company_name".to_string(), "role".to_string(), "apply_url".to_string()]);
            preferred_sources.extend(vec!["company_career_pages".to_string(), "verified_job_boards".to_string()]);
            freshness = "7 days".to_string();
            
            if p_lower.contains("bangalore") || p_lower.contains("bengaluru") {
                constraints.push("location ~= Bangalore".to_string());
            }
        } else {
            entity = format!("{}_business_entity", category);
            fields.insert("entity_name".to_string(), "string".to_string());
            fields.insert("website".to_string(), "url".to_string());
            fields.insert("business_summary".to_string(), "string".to_string());
            fields.insert("key_attributes".to_string(), "string".to_string());
            critical_fields.extend(vec!["entity_name".to_string(), "website".to_string()]);
            preferred_sources.extend(vec!["official_websites".to_string(), "authoritative_directories".to_string()]);
        }

        DataContract {
            entity,
            fields,
            constraints,
            freshness,
            target_count: 20,
            preferred_sources,
            critical_fields,
        }
    }
}
