# FreePing - Game IP List

## Current Games

| Game | Protocol | Ports | IP Ranges |
|------|----------|-------|-----------|
| Valorant | UDP | 7000-7500 | 8 ranges |
| League of Legends | UDP/TCP | 5000-5500, 8393-8400 | 6 ranges |
| Fortnite | UDP | 8000-9000, 9000-9999 | 10 ranges |
| Counter-Strike 2 | UDP | 27000-27050 | 10 ranges |
| Call of Duty: Warzone | UDP | 3074, 3075 | 6 ranges |
| Apex Legends | UDP | 1024-1124, 37000-38000 | 6 ranges |
| Minecraft (Java) | TCP | 25565 | 4 ranges |
| Rainbow Six Siege | UDP | 6000-6500 | 6 ranges |
| GTA Online | UDP | 6672, 61455-61458 | 5 ranges |
| Overwatch 2 | UDP | 6112-6119 | 5 ranges |

## Adding Custom IPs

1. Open FreePing
2. In the "Game Selection" section, enter IPs manually
3. One IP or CIDR range per line
4. Click "Activate Tunnel"

Example:
```
192.168.1.0/24
10.0.0.0/8
203.0.113.5/32
```

## How IPs Are Collected

- Official game server documentation
- Traffic analysis from gaming communities
- Community contributions

## Contributing

To add or update game IPs:

1. Fork the repository
2. Edit `freeping/data/games_list.json`
3. Submit a pull request

Or open an issue with the game name and server IPs.
