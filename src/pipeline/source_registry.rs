use std::collections::HashMap;
use url::Url;

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct DomainProfile {
    pub domain: String,
    pub source_type: String,
    pub trust_tier: String,
    pub authority_score: f32,
    pub schema_reliability: f32,
    pub freshness_score: f32,
}

pub struct SourceRegistry {
    profiles: HashMap<String, DomainProfile>,
}

impl SourceRegistry {
    pub fn new() -> Self {
        let mut profiles = HashMap::new();

        // High Trust Official Portals & Careers
        let official_domains = vec![
            ("careers.google.com", "official_company_page", "primary", 0.98, 0.95),
            ("jobs.apple.com", "official_company_page", "primary", 0.98, 0.95),
            ("amazon.jobs", "official_company_page", "primary", 0.98, 0.95),
            ("microsoft.com", "official_company_page", "primary", 0.97, 0.95),
            ("voyehomes.com", "official_company_page", "primary", 0.95, 0.90),
            ("littlearth.in", "official_company_page", "primary", 0.95, 0.90),
            ("wikipedia.org", "authoritative_encyclopedia", "primary", 0.96, 0.92),
            ("github.com", "authoritative_repository", "primary", 0.95, 0.92),
            ("rust-lang.org", "official_documentation", "primary", 0.99, 0.98),
        ];

        for (dom, st, tt, auth, rel) in official_domains {
            profiles.insert(dom.to_string(), DomainProfile {
                domain: dom.to_string(),
                source_type: st.to_string(),
                trust_tier: tt.to_string(),
                authority_score: auth,
                schema_reliability: rel,
                freshness_score: 0.95,
            });
        }

        // Tier-2 Trusted Industry Platforms
        let industry_platforms = vec![
            ("in.linkedin.com", "primary_job_board", "secondary", 0.88, 0.85),
            ("linkedin.com", "primary_job_board", "secondary", 0.88, 0.85),
            ("in.indeed.com", "primary_job_board", "secondary", 0.85, 0.82),
            ("indeed.com", "primary_job_board", "secondary", 0.85, 0.82),
            ("glassdoor.co.in", "primary_job_board", "secondary", 0.84, 0.80),
            ("naukri.com", "primary_job_board", "secondary", 0.86, 0.80),
            ("shine.com", "primary_job_board", "secondary", 0.82, 0.78),
            ("tripadvisor.com", "verified_directory", "secondary", 0.88, 0.85),
            ("booking.com", "verified_directory", "secondary", 0.88, 0.85),
            ("makemytrip.com", "verified_directory", "secondary", 0.85, 0.80),
        ];

        for (dom, st, tt, auth, rel) in industry_platforms {
            profiles.insert(dom.to_string(), DomainProfile {
                domain: dom.to_string(),
                source_type: st.to_string(),
                trust_tier: tt.to_string(),
                authority_score: auth,
                schema_reliability: rel,
                freshness_score: 0.90,
            });
        }

        Self { profiles }
    }

    pub fn profile_for_url(&self, raw_url: &str) -> DomainProfile {
        let domain = Url::parse(raw_url)
            .map(|u| u.host_str().unwrap_or("").to_lowercase())
            .unwrap_or_default();

        if let Some(profile) = self.profiles.get(&domain) {
            return profile.clone();
        }

        // Heuristic domain profiling
        let (source_type, trust_tier, authority_score, schema_reliability) = if domain.contains("gov") || domain.contains("edu") || domain.contains("org") {
            ("authoritative_institution", "primary", 0.92, 0.88)
        } else if domain.contains("career") || domain.contains("job") || domain.contains("work") {
            ("direct_career_site", "primary", 0.89, 0.85)
        } else if domain.contains("hotel") || domain.contains("resort") || domain.contains("stay") {
            ("hospitality_provider", "primary", 0.87, 0.84)
        } else if domain.contains("news") || domain.contains("times") || domain.contains("express") {
            ("news_wire", "secondary", 0.78, 0.75)
        } else {
            ("general_web_source", "tertiary", 0.70, 0.65)
        };

        DomainProfile {
            domain,
            source_type: source_type.to_string(),
            trust_tier: trust_tier.to_string(),
            authority_score,
            schema_reliability,
            freshness_score: 0.80,
        }
    }
}
