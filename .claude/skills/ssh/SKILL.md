---
name: ssh
description: SSH into remote servers and execute commands. Use for remote operations, file transfers, and server management.
allowed-tools: Bash(ssh*), Bash(scp*), Bash(rsync*), Bash(sshpass*), Read, Write
argument-hint: [host-alias]
---

## SSH Connections

| Alias | Host | User | Password | Hostname | Purpose |
|-------|------|------|----------|----------|---------|
| `deb9` | `10.0.0.48` | `n8n` | `passw0rd` | epyc-deb9 | vera-ai source project |
| `deb8` | `10.0.0.46` | `n8n` | `passw0rd` | epyc-deb8 | vera-ai Docker runtime |

## Connection Commands

**Interactive SSH:**
```bash
sshpass -p 'passw0rd' ssh -o StrictHostKeyChecking=no n8n@10.0.0.48
sshpass -p 'passw0rd' ssh -o StrictHostKeyChecking=no n8n@10.0.0.46
```

**Run single command:**
```bash
sshpass -p 'passw0rd' ssh -o StrictHostKeyChecking=no n8n@10.0.0.48 "command"
sshpass -p 'passw0rd' ssh -o StrictHostKeyChecking=no n8n@10.0.0.46 "command"
```

**Copy file to server:**
```bash
sshpass -p 'passw0rd' scp -o StrictHostKeyChecking=no local_file n8n@10.0.0.48:/remote/path
sshpass -p 'passw0rd' scp -o StrictHostKeyChecking=no local_file n8n@10.0.0.46:/remote/path
```

**Copy file from server:**
```bash
sshpass -p 'passw0rd' scp -o StrictHostKeyChecking=no n8n@10.0.0.48:/remote/path local_file
sshpass -p 'passw0rd' scp -o StrictHostKeyChecking=no n8n@10.0.0.46:/remote/path local_file
```

**Sync directory to server:**
```bash
sshpass -p 'passw0rd' rsync -avz -e "ssh -o StrictHostKeyChecking=no" local_dir/ n8n@10.0.0.48:/remote/path/
sshpass -p 'passw0rd' rsync -avz -e "ssh -o StrictHostKeyChecking=no" local_dir/ n8n@10.0.0.46:/remote/path/
```

**Sync directory from server:**
```bash
sshpass -p 'passw0rd' rsync -avz -e "ssh -o StrictHostKeyChecking=no" n8n@10.0.0.48:/remote/path/ local_dir/
sshpass -p 'passw0rd' rsync -avz -e "ssh -o StrictHostKeyChecking=no" n8n@10.0.0.46:/remote/path/ local_dir/
```

## Notes

- Uses `sshpass` to handle password authentication non-interactively
- `-o StrictHostKeyChecking=no` prevents host key prompts (useful for automation)
- For frequent connections, consider setting up SSH key authentication instead of password

## SSH Config (Optional)

To simplify connections, add to `~/.ssh/config`:

```
Host n8n-server
    HostName 10.0.0.48
    User n8n
```

Then connect with just `ssh n8n-server` (still needs password or key).