# Recall intelligence: model-year match is NOT VIN match

## US and Germany

- NHTSA public API supports model/year recall searching for US-market records.
- The US 2021 BMW 330i record returned seven listed campaigns when checked 2026-11-14. A subset is stored in `data/us_2021_330i_recalls_verified.csv` as **brief metadata only**, not the original complete reports.
- For vehicles in Germany, consult BMW's national VIN checker and the KBA recall database. BMW explicitly cautions that engine/model alone cannot establish exact affected status.

## Model metadata you should collect (without storing VIN unnecessarily)

Market, production month/year, engine/variant, model year, VIN recall lookup result and lookup timestamp. If user volunteers a VIN for an official query, avoid persisting it in general RAG logs.

## Critical handoff

If a relevant campaign is found, flag `recall_requires_vin_verification = true`, include campaign number and official checker URL, and avoid diagnosing it as 'confirmed' until a VIN-specific status is established.

**References:** S021–S028.
