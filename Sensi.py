import os, hashlib
import pandas as pd

#  SETTINGS =================
INPUT_FILE  = r"XXXXXXXXXXXXXX"
OUT_DIR     = os.path.dirname(os.path.abspath(__file__))
SECRET_SALT = "CHANGE_THIS_SECRET"      # keep it OUTSIDE the data, never share it

HASH_COLS   = ["first_name", "last_name", "email", "ip_address",
               "Street Address", "Latitude", "Phone"]
SPECIAL_CAT = ["politic_opinion"]       # Art. 9 special category data



def sha256(v):
    if pd.isna(v):
        return v
    return hashlib.sha256((SECRET_SALT + str(v).strip().lower()).encode("utf-8")).hexdigest()


df = pd.read_csv(INPUT_FILE, dtype=str, encoding="utf-8-sig")
df.columns = [c.strip() for c in df.columns]
print("Rows loaded:", len(df))

# Consent (Art. 6/7) -----
df["consent_given"] = df["Owner_Consent"].str.strip().str.lower().isin(["true", "yes", "1"])

#- DSAR type (Art. 15-18) -----
dsar = df["Dsar_"].str.strip().str.lower()
df["dsar_type"] = dsar.map({
    "access request":        "ACCESS",
    "rectification request": "RECTIFICATION",
    "erasure request":       "ERASURE",
    "restriction request":   "RESTRICTION",
}).fillna("UNKNOWN")

# Decision per row (priority: erasure > restriction > access/rectification) ----------
def decide(r):
    t, c = r["dsar_type"], r["consent_given"]
    if t == "ERASURE":
        return "ERASE - delete all data (Art. 17)"
    if t == "RESTRICTION":
        return "RESTRICT - store only, no processing (Art. 18)"
    if t == "ACCESS":
        return "FULFIL_ACCESS - send copy within 1 month (Art. 15)" if c else \
               "FULFIL_ACCESS + REVIEW_LAWFUL_BASIS - no consent (Art. 15, 6)"
    if t == "RECTIFICATION":
        return "RECTIFY - correct the data (Art. 16)"
    return "REVIEW - unknown request type"

df["gdpr_action"] = df.apply(decide, axis=1)

# Art. 9: special category data without explicit consent must not be kept
df["special_data_unlawful"] = ~df["consent_given"]
df.loc[df["special_data_unlawful"], SPECIAL_CAT] = "[REMOVED - no explicit consent]"

#  SHA-256 of all sensitive data ----------
for c in HASH_COLS:
    df[c] = df[c].apply(sha256)

# Erasure: nothing personal must remain -> keep only an audit stub
erasure_mask = df["dsar_type"] == "ERASURE"

erasure_stub = pd.DataFrame({
    "audtit_id" : range(1 , erasure_mask.sum() + 1),
    "dsar_type" : "ERASURE", 
    "action" : "ERASURE_REQUEST_PROCESSED", 
    "erasure_status" : "COMPLETED",
    "processed_at" : pd.Timestamp.now().strftime("%Y/%m/%D %H:%M:%S"),
    "personal_data_retained" : False
})
df_out = df.loc[~erasure_mask].copy()
# ---------- Export ---------- 
def save(frame, name):
    p = os.path.join(OUT_DIR, name)
    frame.to_csv(p, index=False, encoding="utf-8-sig")
    print(f"{len(frame):>5} rows -> {p} | exists: {os.path.exists(p)}")

save(df_out,                                         "1_processed_hashed.csv")
save(df[df["dsar_type"] == "ACCESS"],                "2_dsar_access.csv")
save(df[df["dsar_type"] == "RECTIFICATION"],         "3_dsar_rectification.csv")
save(df[df["dsar_type"] == "RESTRICTION"],           "4_dsar_restriction.csv")
save(erasure_stub,                                   "5_dsar_erasure_audit_stub.csv")
save(df[~df["consent_given"]],                       "6_no_consent.csv")

print("\n=== AUDIT SUMMARY ===")
print(df["dsar_type"].value_counts().to_string())
print("\nConsent:", df["consent_given"].value_counts().to_dict())
print("\n", df["gdpr_action"].value_counts().to_string())
try:
    os.startfile(OUT_DIR)
except AttributeError:
    pass
