"""Font subsetting script.

Subset NotoSansSC and SSFangTangTi fonts to reduce file size.
Uses fontTools library to generate WOFF2 format subset fonts.

Usage:
    pip install fonttools brotli
    python scripts/subset_fonts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent
FONT_DIR = PROJECT_ROOT / "templates" / "res" / "fonts"
SCRIPT_DIR = PROJECT_ROOT / "scripts"

# GB2312 Level 1 Chinese characters (common characters, ~3500)
# Sorted by pinyin, covers 99% of daily usage scenarios
GB2312_LEVEL1 = """
啊阿埃挨哎唉哀皑癌蔼矮艾碍爱隘鞍氨安俺按暗岸胺案肮昂盎凹敖熬翱袄傲奥懊澳芭疤捌扒叭吧笆八疤巴拔跋靶霸耙坝摆罢佰柏拜百败拜稗扳班般颁板版扮拌伴瓣半办绊邦帮梆榜膀绑棒磅蚌镑傍谤苞胞包褒剥薄雹保堡饱抱报暴豹鲍爆杯碑悲卑北辈背贝倍狈备惫焙被奔苯本笨崩绷甭泵蹦迸逼鼻比鄙笔彼碧蓖蔽毕毙毖币庇痹闭敝弊必辟壁臂避陛鞭边编贬扁便变毕辨辩辫遍标彪膘表鳖憋别瘪彬斌濒滨冰兵柄丙秉饼炳病并玻菠播拨钵波博勃搏铂箔伯帛舶泊渤勃驳柏卜哺补埠不布步簿部怖擦猜裁材才财睬踩采彩菜蔡餐参蚕残惭惨灿苍舱仓沧藏操糙槽曹草厕策侧册测蹭层曾插查茬茶岔碴诧柴豺搀掺蝉馋谗缠铲产阐颤昌猖场尝常长偿肠厂敞畅唱倡超抄钞朝嘲潮巢吵炒扯彻掣尘忱沈沉陈晨衬撑称城橙成呈乘惩澄诚承逞骋秤吃痴持匙池迟驰驰耻侈尺赤翅斥炽充冲虫崇宠憧舂充冲忡聪葱囱匆从丛凑蹴促簇蹿篡窜摧崔催脆瘁粹淬翠村存寸磋撮搓措挫错搭达答瘩打大呆歹傣戴带殆代袋待耽担丹单郸掸胆旦氮但惮淡诞弹蛋当挡党荡档刀捣蹈倒岛祷导到稻悼道盗德得的蹬灯登等瞪凳邓堤低滴迪敌笛狄涤翟嫡抵底地蒂第帝递蒂缔颠滇癫点典垫电巅甸店惦奠淀殿碉叼雕凋刁掉吊钓调跌爹谍蝶叠迭丁盯叮钉顶鼎定订丢东冬董懂动栋侗恫冻洞兜抖斗陡豆逗痘都督毒犊独读堵睹赌杜镀肚度渡妒端短锻段断缎堆兑队对墩吨蹲敦顿囤钝盾遁哆夺朵堕跺舵鄂恩而儿耳迩饵洱二贰发罚筏伐乏阀法珐藩帆番翻樊樊钒繁烦饭范贩犯泛梵芳方肪房防妨仿访纺放菲非啡飞肥匪诽吠肺废沸费芬酚吩氛分纷坟焚汾粉奋份忿愤粪丰封枫蜂峰锋风疯烽逢冯缝讽奉凤佛否夫肤孵扶拂辐幅氟符伏俘服浮涪福袱弗甫抚辅俯釜斧脯腑府腐赴副覆赋复傅付阜父腹负富讣附妇缚咐噶嘎该改概钙盖溉干甘杆柑竿肝赶感秆敢赣冈刚纲缸钢纲港杠杠皋高膏羔糕搞稿告哥歌搁戈鸽胳疙割革格葛阁隔铬个各给根跟耕更庚羹埂耿梗工攻功恭供躬公宫弓巩汞拱贡共钩勾沟苟狗垢构购够辜菇咕箍估沽孤姑鼓古蛊骨谷股雇顾固刮瓜剐寡挂怪乖拐棺官冠观管馆罐贯惯关灌光广规硅归龟闺轨鬼诡癸桂柜跪贵龚贡滚棍锅郭国过哈蛤孩骸氦亥害骇酣憨邯韩涵含函寒喊罕翰撼捍旱憾悍焊汗汉夯杭航壕嚎豪毫郝好号耗浩呵喝荷菏核禾和何合盒貉阂河涸赫褐鹤贺嘿黑痕很狠恨哼亨横衡恒轰哄烘虹鸿洪宏弘红喉侯猴吼厚候后呼乎忽瑚壶葫胡蝴糊湖狐弧虎唬护户沪花哗华猾滑化划画话怀徊淮槐坏欢桓还环换患唤焕豢宦幻荒慌黄磺蝗簧皇凰惶煌晃幌恍谎灰挥辉徽恢蛔回毁悔慧卉惠晦贿秽会烩汇讳诲绘荤昏婚魂浑混豁活伙火获或惑霍货祸击圾基机畸稽积箕肌饥迹激绩姬缉奇畸畿矶羁吉嫉棘籍辑集及急疾汲即嫉级挤几脊己蓟技冀季悸祭继济寄寂计记既忌际妓继纪枷甲钾假稼价架驾嫁歼监坚尖笺间煎兼肩艰奸缄茧检柬碱硷拣捡简俭剪减荐槛鉴践贱见键箭件健舰剑饯渐溅涧建僵姜将浆江疆蒋桨奖讲匠酱降蕉椒礁焦胶交郊浇骄娇嚼搅铰矫侥脚狡角饺绞剿教酵轿较窖叫揭接皆秸街阶截劫桔杰捷睫竭洁结借介懈届诫戒巾斤今金津筋紧锦仅谨进靳晋禁近浸尽劲荆兢茎睛晶鲸京惊精须经井警景颈静境敬镜径痉靖竟竞净炯窘揪究纠玖韭久灸九酒厩救旧臼舅咎就疚鞠拘狙疽居驹菊局咀矩举沮聚拒据巨具距踞锯俱句惧炬剧捐鹃娟倦眷卷铰蹶攫抉掘倔爵觉决诀绝谲菌钧军君峻俊浚郡骏喀咖卡开楷凯慨刊堪勘坎砍看康慷糠扛抗亢炕考拷烤靠坷苛柯棵磕渴科壳咳可刻克客肯垦恳坑吭空恐孔控抠口扣寇枯哭窟苦酷库裤夸垮挎跨胯块筷侩快宽款匡筐狂况旷矿框眶亏岿窥葵奎魁馈亏愧坤捆困括扩廓阔垃拉喇啦蜡腊辣来莱赖蓝婪拦栏篮兰澜揽缆懒览烂郎琅狼粮廊螂朗浪捞劳牢老涝姥乐勒擂雷蕾镭磊累儡垒擂肋类泪棱楞冷厘梨犁黎璃狸离漓理李里鲤礼莉荔吏栗丽厉励砾利立例俐痢立粒沥隶力璃俩联莲怜连涟廉敛脸炼恋链练良粮凉梁粱两辆量晾亮谅撩聊僚疗燎寥撩潦了撂料列烈裂劣猎琳林磷霖临邻鳞淋拎零灵伶铃凌聆菱陵领岭溜流琉硫留馏瘤流柳拢龙聋笼隆垄拢楼娄搂篓漏陋芦颅卢炉掳卤虏鲁麓碌露路赂鹿潞禄录陆戮驴吕铝侣旅履屡缕虑氯律率滤绿峦挛孪滦卵乱掠略抡轮伦仑沦纶论萝螺罗逻锣箩骡裸落洛络骆驼马妈麻玛码蚂马吗埋买麦卖迈脉瞒馒蛮满蔓曼慢漫谩墒芒茫盲氓忙莽猫毛矛茅茂冒帽貌贸么玫枚梅酶霉煤眉媒镁每美妹昧魅寐袂闷门萌蒙檬盟锰猛梦孟眯醚靡糜迷谜弥米靡泌蜜密靡棉眠绵冕免勉娩缅面苗描瞄藐秒渺妙庙灭蔑抿民皿敏悯闽明名鸣螟铭冥眯命谬摸摹蘑模膜磨摩魔抹末沫茉漠寞墨默摩牟谋缪木目牧暮穆募拿呐纳钠娜奶耐奈南男难囊挠脑恼闹淖呢馁嫩能妮霓倪泥尼匿你溺腻尼拈年碾撵念粘娘鸟杳尿捏聂涅镍孽蹑您柠狞凝宁拧牛扭钮纽脓浓农弄奴努怒女暖虐疟挪诺懦欧鸥殴藕呕偶沤爬帕怕琶拍排牌徘湃派攀潘盘磐盼畔判叛乓庞旁耪胖抛咆刨炮袍跑泡呕胚培裴赔陪沛佩配喷盆砰抨烹澎彭蓬棚硼鹏篷癖皮琵疲啤匹坡泼婆魄粕剖扑铺仆莆葡菩蒲埔朴圃普浦谱曝瀑期欺栖戚七沏漆漆祈齐骑棋奇歧畦崎旗乞企起启气弃汽契砌器祁迄泣凄戚恰洽牵扦钎铅千迁签仟谦乾黔钱钳前潜遣浅谴堑嵌欠歉枪呛羌墙蔷强抢悄桥瞧乔侨巧窍撬翘俏峭切茄且怯窃沁亲琴芹秦禽勤侵寝钦沁圈蜷泉拳眷全痊诠犬券劝缺阙瘸却确榷雀裙群逡燃冉染嚷壤攘扰绕惹热壬仁人忍韧任认刃妊纫扔仍日戎茸蓉荣融溶熔绒冗柔揉茹蠕儒孺入辱褥软阮蕊瑞锐润闰弱撒洒萨腮鳃塞赛三叁伞散桑嗓丧搔骚扫嫂瑟色涩森僧莎砂杀刹沙纱傻啥煞筛晒珊苫杉山删煽衫闪陕赡缮善珊擅膳熵伤殇商赏晌上尚梢捎稍烧绍勺芍鞘韶少哨邵绍奢赊蛇舌折舍赦摄射慑涉社设砷申呻伸身深娠绅神沈审婶肾渗甚慎渗生声牲胜笙甥升盛尸失师施湿诗狮尸十石拾时什食蚀实识史矢使屎驶始式示士世柿事拭誓逝势是嗜噬适仕侍释饰氏市恃室是视试诗手首寿受授售兽熟赎抒叔枢淑殊梳舒疏淑输蔬墅抒暑鼠数薯曙术梳树竖恕庶数墅刷耍唆率摔衰甩帅栓拴霜双爽谁水睡税吮瞬顺舜说硕朔烁斯撕嘶思私司丝死肆寺嗣四伺似饲巳厮耸松讼颂送宋诵搜艘擞苏酥俗素速粟僳塑溯诉肃酸蒜算虽隋随髓岁碎穗遂隧祟孙损笋荪逊唆缩琐所索塌他它她塔獭挞蹋踏胎苔摊台泰酞太态汰坍摊贪滩瘫坛檀痰潭谭谈坦毯袒碳探叹炭汤塘搪堂棠膛丹糖躺趟烫掏涛滔绦萄桃逃淘陶讨套特藤腾疼誉梯剔踢锑提题蹄啼体替嚏涕惕屉剃涕天添填田恬腆挑条迢眺跳贴铁帖厅听烃汀廷停亭庭挺艇通桐酮瞳同铜彤童桶捅筒统痛偷投头透凸秃突图徒途涂屠土吐兔湍团推颓腿蜕褪退吞屯臀拖托脱驼陀驮驼椭妥拓唾蛙挖娃瓦歪外豌弯湾玩顽丸烷完碗挽晚皖惋宛婉腕汪亡王网枉旺往忘妄魏微危威巍韦违桅围唯惟潍尾纬委萎萎威卫未伟伪纬胃喂魏味畏渭猥尉慰瘟温蚊纹闻文稳问翁嗡窝蜗挝倭褒沃卧握幌巫呜钨乌污误屋无芜梧吾吴捂吾梧坞五伍午伍武侮捂舞梧务悟戊晤物勿捂恶西昔熙析汐惜烯晰媳吸锡牺稀息希悉膝夕惜熄烯溪锡嬉檄牺袭席习媳铣洗系隙细戏瞎虾匣霞辖暇峡侠狭下厦夏吓掀锨先仙鲜纤咸贤衔舷闲涎嫌显险现献县腺馅羡宪陷限线鲜镶厢湘箱襄详祥翔响享县项巷橡像向象萧硝霄削哮嚣销消宵肖晓笑效楔些歇蝎鞋协挟携邪斜胁谐写械卸蟹懈泄泻谢屑薪芯锌欣辛新忻心信衅星腥猩惺兴刑型形邢行幸杏性姓兄凶胸匈汹雄熊休修羞朽嗅锈秀袖绣墟戌需虚嘘须徐许吁戌墟旭序叙恤绪续轩宣谞萱喧玄悬旋选癣眩绚玄玄穴学勋熏循旬询寻驯巡讯逊迅压押鸦鸭呀丫芽牙崖涯雅哑亚讶焉咽阉烟淹盐严研蜒岩延延颜阎炎沿演眼厌砚雁谚彦验焰艳厌燕雁秧央殃扬杨羊阳羊氧仰痒养样漾邀腰妖瑶摇尧遥窑谣姚咬耀药要耀耶爷野叶业叶页曳夜液腋一衣医依颐夷遗移仪胰疑沂宜姨彝椅蚁倚已乙矣以艺抑易邑屹译役毅逸疫亿谊义忆仪夷乙溢肄裔亦逸翌绎茵音因姻殷银吟寅淫尹饮隐印瘾映英樱婴鹰莺应缨莹萤营荧迎赢盈影颖硬映哟拥佣臃痈庸雍踊蛹咏壅涌泳永佑右尤尤邮由犹油游酉有友右诱又幼迂于舆余鱼俞榆渔隅逾娱愉渝虞愚舆禹宇羽雨屿语玉喻峪愈欲浴寓裕预豫驭鸳渊冤元垣袁原源辕猿缘圆垣园员圆怨远愿院苑远怨院约月跃钥岳粤悦阅跃曰约晕云匀允陨韵孕蕴酝赃臧凿早枣蚤澡藻躁噪皂灶躁责择泽则贼增憎曾赠扎札轧铡闸眨栅榨咋乍炸摘窄斋债寨瞻毡詹粘沾盏斩辗崭展栈湛绽崭占战站蘸绽瞻章张彰漳胀仗帐账障涨丈杖胀账仗昭招找爪赵罩兆肇召遮折哲蛰辙者锗蔗这浙摘褶真贞侦针珍臻斟甄疹诊枕振赈镇震阵真圳蒸怔挣睁征狰争挣峥铮证郑政帧症怔正止支枝吱翅知之织肢脂执直侄值指职植旨纸酯抵止趾挚掷峙制智帜质置致峙治窒滞中忠终钟肿衷仲种重仲众舟周州洲粥诌轴肘帚咒皱宙昼骤诛朱珠株蛛诸逐竹烛煮拄瞩嘱主著助蛀贮铸筑住注祝驻抓爪拽专砖转撰赚篆妆壮撞幢桩状椎锥追赘坠缀谆准捉拙卓桌灼琢茁酌啄着浊咨姿兹淄孜紫仔籽子自渍字谆踪综棕鬃踪卒族祖诅阻组钻纂攥嘴最罪醉尊遵昨左佐柞做作坐座
"""

# Fortune fixed text (extracted from fortune/core.py)
FORTUNE_FIXED_CHARS = """
凶末吉小中大超今日运势
长夜再暗火种仍在转机终会到来
微光不灭步步向前黎明就在眼前
心怀希冀顺流而行好事悄然靠近
逆境翻篇机遇迎面惊喜不期而至
小吉随身难题化易幸运与你并肩
吉星高照所行皆坦所愿皆如愿
福泽深厚大吉加身一路花开有声
七星同耀奇迹频现万事皆成
的运势
Support By AstrBot
"""

# ASCII characters, numbers, common punctuation
ASCII_PUNCTUATION = """
abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
0123456789
！？。，、；：""''（）【】《》—…·
!"#$%&'()*+,-./:;<=>?@[\\]^_{|}~
★☆
"""


def generate_chars_file() -> Path:
    """Generate character set file."""
    chars_file = SCRIPT_DIR / "chars.txt"

    # Merge all characters, deduplicate
    all_chars = set()
    for char in GB2312_LEVEL1 + FORTUNE_FIXED_CHARS + ASCII_PUNCTUATION:
        if char.strip():  # Skip whitespace
            all_chars.add(char)

    # Write file
    chars_file.write_text("".join(sorted(all_chars)), encoding="utf-8")
    print(f"[+] Generated chars file: {chars_file}")
    print(f"    Total unique chars: {len(all_chars)}")

    return chars_file


def subset_font_with_api(
    input_font: Path,
    output_font: Path,
    chars: str,
) -> bool:
    """Subset font using fontTools API."""
    try:
        from fontTools.subset import Subsetter
        from fontTools.ttLib import TTFont

        # Load font
        font = TTFont(str(input_font))

        # Create subsetter
        subsetter = Subsetter()

        # Set characters to keep
        subsetter.populate(text=chars)

        # Execute subsetting
        subsetter.subset(font)

        # Export as WOFF2
        font.flavor = "woff2"
        font.save(str(output_font))

        # Close font
        font.close()

        return True
    except Exception as e:
        print(f"[-] Failed to subset {input_font.name}: {e}")
        return False


def main():
    """Execute font subsetting."""
    print("=" * 60)
    print("Font Subsetting Script")
    print("=" * 60)

    # Check if fonttools is installed
    try:
        from fontTools.ttLib import TTFont  # noqa: F401
    except ImportError:
        print("[-] fontTools not installed. Run: pip install fonttools brotli")
        sys.exit(1)

    # Generate character set file
    chars_file = generate_chars_file()
    chars = chars_file.read_text(encoding="utf-8")

    # Font configuration
    fonts_to_process = [
        {
            "input": "NotoSansSC-Regular.otf",
            "output": "NotoSansSC-Regular.woff2",
        },
        {
            "input": "NotoSansSC-Bold.otf",
            "output": "NotoSansSC-Bold.woff2",
        },
        {
            "input": "SSFangTangTi.ttf",
            "output": "SSFangTangTi.woff2",
        },
    ]

    # Statistics
    total_original = 0
    total_subset = 0

    print("\nProcessing fonts:")
    print("-" * 60)

    for font_config in fonts_to_process:
        input_path = FONT_DIR / font_config["input"]
        output_path = FONT_DIR / font_config["output"]

        if not input_path.exists():
            print(f"[!] Input font not found: {input_path}")
            continue

        # Record original size
        original_size = input_path.stat().st_size

        # Execute subsetting
        print(f"[+] Subsetting: {input_path.name}")
        success = subset_font_with_api(input_path, output_path, chars)

        if success:
            subset_size = output_path.stat().st_size
            reduction = (1 - subset_size / original_size) * 100

            print(f"    Original: {original_size / 1024 / 1024:.2f} MB")
            print(
                f"    Subset:   {subset_size / 1024:.1f} KB "
                f"({subset_size / 1024 / 1024:.2f} MB)"
            )
            print(f"    Reduction: {reduction:.1f}%")

            total_original += original_size
            total_subset += subset_size
        else:
            print(f"[-] Failed: {input_path.name}")

    # Output summary
    print("\n" + "=" * 60)
    print("Summary:")
    print("-" * 60)
    if total_subset > 0:
        total_reduction = (1 - total_subset / total_original) * 100
        print(f"Total Original: {total_original / 1024 / 1024:.2f} MB")
        print(
            f"Total Subset:   {total_subset / 1024:.1f} KB "
            f"({total_subset / 1024 / 1024:.2f} MB)"
        )
        print(f"Total Reduction: {total_reduction:.1f}%")
        print("\n[+] Font subsetting completed successfully!")
        print("[!] Remember to update fortune/renderer.py to use .woff2 files")
    else:
        print("[!] No fonts were processed successfully")
        sys.exit(1)


if __name__ == "__main__":
    main()
