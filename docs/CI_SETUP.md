# CI setup: GitLab now, GitHub later

## 1. Create the project and push

```bash
git init -b main
git add . && git commit -m "Add AI-defined test sampling package"
git remote add origin <your-gitlab-project-url>
git push -u origin main
git switch -c develop && git push -u origin develop
```

## 2. Create the CI/CD variables (Settings > CI/CD > Variables)

| Variable | Notes |
|---|---|
| `SONARQUBE_TOKEN` | Masked. Do not mark as protected, or feature branches will not see it |
| `SONARQUBE_URL` | URL of the SonarQube server or SonarCloud |
| `SONAR_PROJECT_KEY` | SonarQube project identifier |

Enter them in the GitLab UI only. Never put them in the repository, a chat or a ticket. If one is
ever exposed, revoke and recreate it.

Trivy and Gitleaks need no token.

## 3. Find out which runner you have

Run the pipeline from the UI: **Build > Pipelines > Run pipeline**, add the variable
`RUNNER_PROBE` = `true`, and read the log of the job `runner-probe`.

| Log says | Meaning | What to do |
|---|---|---|
| `docker executor` | Jobs run in the images named in the pipeline | Nothing, this pipeline is built for it |
| `shell or other executor` | `image:` is ignored; jobs run on the runner host | Ask the runner owner for a Docker executor, or install Python 3.12, ruff, Gitleaks, Trivy and the Sonar scanner on that host |

If you use GitLab.com shared runners, you have Docker executors.

## 4. What the first run does

| Job | Stage | Expected on the first run |
|---|---|---|
| `lint-code` | lint | passes |
| `test-validators` | test | passes; fails below 80% line coverage |
| `security-sonarqube` | security | **fails until the three variables exist** (mandatory gate, on purpose) and until the quality gate passes |
| `security-trivy-fs` | security | blocks on CRITICAL, reports HIGH |
| `security-gitleaks` | security | blocks on any secret |
| `package-skill-int / uat / prod` | package | only on `develop`, `release/*`, `main`; artifact kept 7 days / 30 days / 1 year |

Branch triggers follow the org conventions: `feature/*`, `bugfix/*`, `hotfix/*` and merge requests
run lint, test and security; `develop`, `release/*` and `main` also package. There is nothing to
build, publish or deploy, so those stages are intentionally absent and there are no approval gates.

Image versions are pinned in `ci/sampling.yml` (`variables:`). If a tag cannot be pulled on your
runner, change it there.

## 5. Move to GitHub later

1. Push the same repository. The workflow is `.github/workflows/ci-sampling.yml`; `.gitlab-ci.yml`
   and `ci/` are ignored by GitHub and can stay or be removed.
2. Create the repository secrets `SONARQUBE_TOKEN`, `SONARQUBE_URL`, `SONAR_PROJECT_KEY`.
3. `gitleaks/gitleaks-action` may need a `GITLEAKS_LICENSE` secret on organisation accounts. Check
   with the owner of the GitHub organisation.
4. Check the Valtech policy for allowed third-party actions before the first run.
5. Create branches `develop` and `main` (and `release/*` when needed) to get the same behaviour.

## 6. Checklist of what a human still has to do

- [ ] Create the three SonarQube variables or secrets
- [ ] Run the runner probe and confirm a Docker executor
- [ ] Confirm the pinned image tags can be pulled (`variables:` in `ci/sampling.yml`)
- [ ] Decide on the coverage and quality-gate exceptions, if any, with the owner of the policy
- [ ] Upload `test-sampling-agent.skill` to the Claude workspace
