-- Processed review data, aggregates and analysis outputs served by backend/app.py
DROP TABLE IF EXISTS reviews, issues, topics, monthly, claims, docs CASCADE;

CREATE TABLE reviews (
  review_id       text PRIMARY KEY,
  status          text NOT NULL,          -- completed | quarantined
  reason          text,                   -- quarantine reason
  topic           text,
  issue_id        text,                   -- topic.subtopic (complaints/cancellations are ranked members)
  intent          text,
  severity        smallint,
  sentiment       real,
  evidence_quote  text,
  quote_source    text,
  needs_review    boolean,
  entities        text,
  cache_source_id text,
  config_id       smallint,               -- -> docs.label_configs (saves ~50 MB vs repeating the string)
  request_id      text,
  rating          smallint,               -- source metadata only (never used to label)
  review_ts       timestamp,
  app_version     text,
  likes           integer,
  review_text     text,                   -- original text (truncated to 1,000 chars for storage)
  v_topic         text,                   -- independent verifier labels (declared sample only)
  v_intent        text,
  v_severity      smallint
);

CREATE TABLE issues (
  issue_id text PRIMARY KEY, rank integer, topic text, title text, description text,
  complaint_count integer, severity_sum integer, mean_severity text, priority_score integer,
  cancellations integer, severity_4_or_5 integer, needs_review integer, one_star integer,
  example_review_ids jsonb, named_by text
);

CREATE TABLE topics (
  topic text PRIMARY KEY, completed_reviews integer, complaint_count integer, severity_sum integer,
  mean_severity text, cancellations integer, sev1 integer, sev2 integer, sev3 integer, sev4 integer, sev5 integer,
  praise integer, request integer, unclear integer
);

CREATE TABLE monthly (month text, topic text, complaints integer, month_rows integer, month_completed integer,
                      month_complaints integer, PRIMARY KEY (month, topic));

CREATE TABLE claims (claim_id text PRIMARY KEY, scope text, issue_id text, metric text, value text, source text);

CREATE TABLE docs (key text PRIMARY KEY, value jsonb NOT NULL);   -- memo, run summary, evals, cost report
