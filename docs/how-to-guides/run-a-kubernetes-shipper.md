# Run a Kubernetes shipper

Use a separate profile file for each restricted shipper process. The process
must receive its indexer credentials through the environment. Do not put
credentials in the profile.

Create a profile for fictional workloads:

```json
{
  "version": 1,
  "plugin": "kube_logs",
  "poll_interval": 5,
  "targets": [
    {
      "namespace": "example-namespace",
      "deployment": "example-deployment",
      "container": "example-container",
      "index": "example-index",
      "source": "example-deployment/example-container",
      "sourcetype": "logfmt"
    }
  ]
}
```

Set `SIEMATIC_AGENT_PROFILE` to the mounted file path. Set
`INDEXER_USERNAME` and `INDEXER_PASSWORD` in the process environment. The
loader rejects a missing file, malformed JSON, unknown plugin, missing field,
duplicate target, or missing credential before the collector starts.

The profile can use a selector instead of a deployment name when the
collector must find a pod by labels. The target still needs a namespace,
container, index, source, and sourcetype.
