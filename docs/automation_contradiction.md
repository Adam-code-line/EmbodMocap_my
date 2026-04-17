 只要你按当前推荐的方式跑（embodmocap-scene-auto.service 的 ExecStart 里用 --mode skip），自动化不会重复跑已经成功完成的      
  step，也不会和你之前已经跑通的结果冲突；它只会在“缺输出/输出不完整”时补跑或修复。                                            
                                                                                                                               
  关键点分三层：                                                                                                               
                                                                                                                               
  1. Ingest（搬运/归档 ZIP）是幂等的                                                                                           
                                                                                                                               
  - auto_spectacular_rec_service.py 只处理 DATA_ROOT/_incoming/*.zip。                                                         
  - --mode skip 时：                                                                                                           
      - scene zip 如果 DATA_ROOT/<SCENE>/ 里 raw 输入已齐，会把新来的 zip 归档到 DATA_ROOT/<SCENE>/seq0/_imports/，不会覆盖已有        数据。                                                                                                                 
      - human zip 如果 DATA_ROOT/<SCENE>/<SEQ>/recording_*.zip 已存在，会把重复上传归档到 DATA_ROOT/<SCENE>/<SEQ>/_imports/，不        会覆盖已有 raw1/raw2 或下游结果。                                                                                      
                                                                                                                               
  2. 跑 pipeline step 是否执行由 run_stages.py --mode skip + anchors 决定                                                      
                                                                                                                               
  - run_stages.py 对每个 step 都有“是否已完成”的判断（anchors 文件/目录存在就跳过）。                                          
  - 所以在 --mode skip 下，已有 transforms.json、mesh_raw.ply、v*/cameras_colmap.npz、optim_params.npz 等输出时，对应 step 会打    印 Skip ... 并跳过，不会重算/覆盖。                                                                                        
                                                                                                                               
  3. 你现在的自动化额外做了两件“避免冲突”的事                                                                                  

  - --lock_dir _locks：同一 scene 串行化，避免 Step3/Step8 这类写同一目录的并发互相覆盖（这是你之前出现半成品 database.db 的高 
    风险来源）。                                                                                                               
  - --log_dir _logs/...：每个 scene/每个 step 的 stdout/stderr 落盘，不影响已有结果，只增加可追溯性。                          
                                                                                                                               
  需要明确的“例外”（不是冲突，是修复）：                                                                                       
                                                                                                                               
  - 如果 Step3 的 database.db 是半成品（比如你现在这种 image-list.txt=193 但 db images=1），自动化会把它判定为“无效”，并触发   
    Step3 overwrite 重建，这是为了避免 Step8 必然报 Sparse model image ... not found。这类情况下你看到的是“文件存在但其实没成  
    功”，不是“重复跑成功 step”。                                                                                               
                                                                                                                               
  怎么一键自检你当前服务是否会重复跑（看 ExecStart）：                                                                         
                                                                                                                               
  systemctl --user show embodmocap-scene-auto.service -p ExecStart --no-pager                                                  
                                                                                                                               
  确认里面是 --mode skip（而不是 --mode overwrite）。                                                                          
                                                                                                                               
  补充提醒：docs/automation_services_ops_zh.md 只是运维文档，不会改变任何已有结果；真正决定行为的是你服务器上的 systemd unit   
  ExecStart 参数。