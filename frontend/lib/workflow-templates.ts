import type { DataContract } from "./api";

export const WORKFLOW_TEMPLATES: { id: string; name: string; description: string; category: string; prompt: string; contract: Partial<DataContract> }[] = [
  { id: "wf-corporate-sponsorship", name: "Corporate sponsorship and CSR", description: "Collect companies with explicit sponsorship evidence.", category: "Sponsorship",
    prompt: "Find 10 companies with documented STEM event sponsorship. Include company name, location and sponsorship evidence.",
    contract: { entity_type: "company", target_count: 10, fields: [
      { name: "company_name", field_type: "string", required: true }, { name: "location", field_type: "location", required: true },
      { name: "sponsorship", field_type: "string", required: true }] } },
  { id: "wf-tech-hiring", name: "Official careers role extraction", description: "Collect distinct openings with employer and location evidence.", category: "Recruitment",
    prompt: "Find 20 current backend engineering job openings. Include job title, employer, location, application URL and published salary when available.",
    contract: { entity_type: "job", target_count: 20, fields: [
      { name: "job_title", field_type: "string", required: true }, { name: "company_name", field_type: "string", required: true },
      { name: "location", field_type: "location", required: true }, { name: "job_url", field_type: "url", required: true },
      { name: "salary", field_type: "currency", required: false }] } },
  { id: "wf-saas-pricing", name: "SaaS pricing and feature matrix", description: "Capture explicit plan prices and billing terms.", category: "Market data",
    prompt: "Find 10 SaaS pricing plans with product name, vendor, price, currency and billing period. Leave unpublished prices unknown.",
    contract: { entity_type: "product", target_count: 10, fields: [
      { name: "product_name", field_type: "string", required: true }, { name: "manufacturer", field_type: "string", required: true },
      { name: "price", field_type: "currency", required: true }, { name: "billing_period", field_type: "string", required: true }] } },
  { id: "wf-supplier-shortlist", name: "Industrial supplier discovery", description: "Collect suppliers with supported locations and certification claims.", category: "Supply chain",
    prompt: "Find 15 industrial component suppliers. Include company name, location, catalog URL and certifications supported by source text.",
    contract: { entity_type: "supplier", target_count: 15, fields: [
      { name: "company_name", field_type: "string", required: true }, { name: "location", field_type: "location", required: true },
      { name: "catalog_url", field_type: "url", required: false }, { name: "certifications", field_type: "certification", required: false }] } },
];
