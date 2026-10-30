# Convenience targets for local work. Render and CI do not use this file.
.PHONY: install dev-api dev-web test test-api test-web accept capture clean

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install --no-audit --no-fund

dev-api:
	cd backend && uvicorn app.main:app --reload --port 8000

dev-web:
	cd frontend && node scripts/serve.mjs

test: test-api test-web

test-api:
	cd backend && python -m pytest -q

test-web:
	cd frontend && node --test tests/app.test.mjs

# Full acceptance suite against the reference plants, with the report written out.
accept:
	cd backend && python -c "from app.services.validation_service import get_validation_service as V;\
	r=V().report('IX-OB-01', gate='G1', tests_pass=True);\
	open('../'+r['filename'],'w').write(r['markdown']);\
	print(r['overall_verdict'], r['characters'], 'characters ->', r['filename'])"

# Refresh the desk's offline payloads from a running backend (resumable).
capture:
	cd frontend && node scripts/capture-mock.mjs http://localhost:8000

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	find . -name '.pytest_cache' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -f Acceptance_Test_Report_*.md pytest-report.xml
