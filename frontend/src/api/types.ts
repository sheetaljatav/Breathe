/** Backend response types. Keep in sync with backend/*/serializers.py. */

export interface OrganizationDTO {
  id: number;
  name: string;
  slug: string;
}

export interface MembershipDTO {
  organization: OrganizationDTO;
  role: "analyst" | "admin";
}

export interface UserDTO {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  memberships: MembershipDTO[];
}

export type SourceType = "sap" | "utility" | "travel";
export type BatchStatus = "queued" | "parsing" | "complete" | "failed";

export interface IngestionBatchDTO {
  id: number;
  source_type: SourceType;
  file_name: string;
  file_sha256: string;
  file_size_bytes: number;
  parser_version: string;
  status: BatchStatus;
  rows_total: number;
  rows_ok: number;
  rows_failed: number;
  uploaded_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string;
  deduped?: boolean;     // present when upload returns an existing batch
}

export interface ParseErrorDTO {
  id: number;
  line_number: number;
  error_code: string;
  field_path: string;
  message: string;
  raw_excerpt: unknown;
}

export interface IngestionBatchDetailDTO extends IngestionBatchDTO {
  errors: ParseErrorDTO[];
}

export interface CanonicalUnitDTO {
  id: number;
  code: string;
  label: string;
  dimension: string;
}

export interface EmissionCategoryDTO {
  id: number;
  code: string;
  label: string;
  scope: 1 | 2 | 3;
  default_unit: CanonicalUnitDTO;
  ghg_protocol_ref: string;
}

export interface EmissionFactorDTO {
  id: number;
  category: EmissionCategoryDTO;
  region: string;
  year: number;
  unit: CanonicalUnitDTO;
  kg_co2e_per_unit: string;     // Decimal serialized as string
  source: string;
  effective_from: string;
  effective_to: string | null;
}

export type ReviewState = "pending" | "flagged" | "approved" | "rejected" | "locked";

export interface ActivityRecordDTO {
  id: number;
  scope: 1 | 2 | 3;
  category: EmissionCategoryDTO;
  activity_date: string;
  period_start: string | null;
  period_end: string | null;
  value: string;
  unit: CanonicalUnitDTO;
  emission_factor: EmissionFactorDTO | null;
  emissions_kg_co2e: string | null;
  facility_code: string;
  notes: string;
  review_state: ReviewState;
  reviewed_by: number | null;
  reviewed_at: string | null;
  locked_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  source_type: SourceType | null;
  batch_id: number | null;
}

export interface AnomalyHintDTO {
  code: string;
  message: string;
  severity: "info" | "warn" | "block";
}

export interface ActivityRecordDetailDTO extends ActivityRecordDTO {
  hints: AnomalyHintDTO[];
  raw_payload?: unknown;
  source_line?: number;
}

export interface OverviewDTO {
  totals: {
    kg_co2e: number;
    pending: number;
    flagged: number;
    approved: number;
    locked: number;
  };
  by_scope: { scope: 1 | 2 | 3; kg_co2e: number; rows: number }[];
  last_batch: { id: number; source_type: SourceType; uploaded_at: string; status: BatchStatus } | null;
}

export interface PlantCodeDTO {
  id: number;
  code: string;
  facility_name: string;
  country: string;
}

export interface AirportDTO {
  iata: string;
  name: string;
  city: string;
  country: string;
  latitude: string;
  longitude: string;
}

export interface PaginatedDTO<T> {
  next: string | null;
  previous: string | null;
  results: T[];
}
