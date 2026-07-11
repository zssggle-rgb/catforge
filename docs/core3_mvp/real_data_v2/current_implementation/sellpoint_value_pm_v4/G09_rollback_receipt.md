# G09 回滚演练回执

## 回滚真值

- 回滚包：`predeploy-runtime.tar.gz`；
- SHA-256：`dba311341c081840a78a69179e365bc48882be74470c5c97c4172f0e0a1d3f0a`；
- 大小：86,611 bytes；
- 包含部署前实际存在的 6 个运行时文件；
- `claim_value_pm_v4_answer.py`、`claim_value_pm_v4_schemas.py`、`claim_value_pm_v4_service.py` 部署前不存在，回滚动作是精确删除这 3 个路径。

## 演练结果

1. 6 个旧文件逐一恢复到主机与 API 容器；
2. 3 个 V4 新文件在主机与容器均删除；
3. API 重启后 health/ready 通过；
4. CLI help 不再出现 `sellpoint-value-pm-v4`；
5. 旧 `sellpoint-value-pm` 对 65E7Q 返回 `status=ok`；
6. 再从同一已校验 RC stage 恢复 9 个文件；
7. API 再次重启后 9/9 hash 与 RC manifest 一致；
8. 无 flag 拒绝、自然语言旧路由、显式 V4 result hash 和 V2 业务结果全部恢复到演练前状态。

## 部署前旧文件 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `catforge_analyst.py` | `191e51729ad3be3ffe13d05225d500ae678e6cb761ded2c3af9f6b8be462d059` |
| `ability_registry.py` | `f9e09bb97b4f87455db6f5e6efdf3643d54b02fff4d086edef1234a8e57e8040` |
| `analyst_repository.py` | `161bb2898f314f35869da8a9f02c774752e03c6ef98ec1440a31b1687cb78969` |
| `analyst_service.py` | `788b4298b70f3fc34623a4a4ef1ef941503d69148c2f0009bd66c147d1dad632` |
| `atomic_handlers.py` | `807b80c7235f63d9612483fda1bc45badfbc732a79023616020cd3e53c9beee2` |
| `sop_orchestrators.py` | `d1974b4357f555576e09f8f666b34b1e054443db92f013ede91f853d57544d2a` |

## 最终状态

205 当前处于 RC 影子态，不是回滚旧态；V4 继续默认关闭。回滚包保留在服务器 `/opt/catforge/.g09/sellpoint-value-pm-v4-rc1-1653bff/`，本地副本已做相同 SHA-256 校验。
