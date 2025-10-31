# RBAC Configuration for RPOD API

## What is RBAC?

RBAC (Role-Based Access Control) is Kubernetes' permission system. It controls **what actions** different entities can perform in the cluster.

## Why Do We Need It?

The `rpod-api` pod needs to:
1. **Create pods** (launch RStudio instances for users)
2. **Delete pods** (stop user sessions)
3. **Create services** (expose RStudio on NodePorts)
4. **List/check pods** (check if user's session is running)

By default, pods have **NO permissions** to interact with the Kubernetes API. We must explicitly grant these permissions.

## Components

### 1. ServiceAccount (`rpod-api`)
- **What**: An identity for the API pod (like a "bot user")
- **Why**: Pods need an identity to authenticate with k8s API
- **Usage**: The API deployment specifies `serviceAccountName: rpod-api`

### 2. Role (`rpod-api-role`)
- **What**: A list of permissions (verbs + resources)
- **Why**: Defines *what* the ServiceAccount can do
- **Permissions granted**:
  - `pods`: get, list, watch, create, delete
  - `services`: get, list, watch, create, delete
  - `pods/log`: get (for debugging)
  - `pods/status`: get (for health checks)

### 3. RoleBinding (`rpod-api-binding`)
- **What**: Connects the ServiceAccount to the Role
- **Why**: Activates the permissions
- **Effect**: Grants `rpod-api` ServiceAccount the permissions in `rpod-api-role`

## Security Considerations

✅ **Least Privilege**: Only grants permissions needed for the API to function
✅ **Namespace-scoped**: Permissions only apply to `default` namespace
✅ **No cluster-wide access**: Cannot affect other namespaces
✅ **Read-only where possible**: Only destructive actions are create/delete

⚠️ **Note**: The API can create/delete ANY pod in the namespace, not just RStudio pods. For production, consider:
- Using a dedicated namespace (e.g., `rstudio-system`)
- Adding label selectors to limit scope
- Implementing audit logging

## Verification

After applying RBAC manifests:
```bash
# Apply RBAC
kubectl apply -f k3s/manifests/rbac.yaml

# Verify configuration
./k3s/prep/verify-rbac.sh

# Manual verification
kubectl auth can-i create pods --as=system:serviceaccount:default:rpod-api
kubectl auth can-i delete services --as=system:serviceaccount:default:rpod-api
```

## Troubleshooting

### Error: "pods is forbidden"
- RBAC not applied: `kubectl apply -f k3s/manifests/rbac.yaml`
- Wrong namespace: Check API deployment uses `namespace: default`
- ServiceAccount not specified: Check deployment has `serviceAccountName: rpod-api`

### Error: "cannot create resource 'pods'"
- Role permissions missing: Check Role has `create` verb for `pods`
- RoleBinding not applied: Check binding connects SA to Role

### How to check what permissions a ServiceAccount has:
```bash
kubectl describe rolebinding rpod-api-binding
kubectl describe role rpod-api-role
```
