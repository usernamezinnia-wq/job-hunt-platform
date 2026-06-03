# -*- coding: utf-8 -*-
"""
求职助手 - Flask Python 全功能后端服务
支持：
1. 跨域资源共享 (CORS) 与 React 前端完美协作
2. 开箱即用支持：支持默认轻量 SQLite、同时一键快速切换至 MySQL
3. 接口规范：岗位检索加载与录入、一键投递申请记录、招聘即时聊天消息保存
"""

import os
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
# 开启全身跨域支持，允许 React (默认 3000 端口或任意外链地址) 访问后端接口
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ==========================================
# 数据库配置选择 (SQLite / MySQL)
# ==========================================
# 默认使用本地便捷内置 SQLite，方便开箱即用免配置直接启动
# 在生产或本地有 MySQL 时，可以将下面的 USE_MYSQL 设为 True
USE_MYSQL = False

if USE_MYSQL:
    # 请根据您的实际 MySQL 连接信息配置
    MYSQL_USER = "root"
    MYSQL_PASSWORD = "your_password"
    MYSQL_HOST = "127.0.0.1"
    MYSQL_PORT = "3306"
    MYSQL_DB = "job_helper"
    app.config[
        "SQLALCHEMY_DATABASE_URI"] = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
else:
    # 默认 SQLite 路径 (自动产生于工程根目录)
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "job_helper.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# ==========================================
# 数据库 ORM 模型定义 (自动建表)
# ==========================================

class Job(db.Model):
    """岗位表"""
    __tablename__ = "jobs"
    id = db.Column(db.String(50), primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    salary = db.Column(db.String(50), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    size = db.Column(db.String(50))
    industry = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(500))  # 以 JSON 串或逗号分割存储 (格式: "北京·中关村,3-5年,本科")
    recruiter_name = db.Column(db.String(50), nullable=False)
    recruiter_title = db.Column(db.String(100), nullable=False)
    recruiter_avatar = db.Column(db.String(255))
    recruiter_bio = db.Column(db.Text)
    job_description = db.Column(db.Text)
    perks = db.Column(db.String(500))  # 逗号分割
    is_hot = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        # 拆分 tags 兼容前端数组
        tag_list = [t.strip() for t in self.tags.split(",")] if self.tags else []
        perk_list = [p.strip() for p in self.perks.split(",")] if self.perks else []
        return {
            "id": self.id,
            "title": self.title,
            "salary": self.salary,
            "company": self.company,
            "size": self.size,
            "industry": self.industry,
            "tags": tag_list,
            "recruiterName": self.recruiter_name,
            "recruiterTitle": self.recruiter_title,
            "recruiterAvatar": self.recruiter_avatar,
            "recruiterBio": self.recruiter_bio,
            "jobDescription": self.job_description,
            "perks": perk_list,
            "isHot": self.is_hot
        }


class Application(db.Model):
    """投递记录表"""
    __tablename__ = "applications"
    id = db.Column(db.String(50), primary_key=True)
    job_id = db.Column(db.String(50), db.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(50), default="applied")  # applied | chatting | interviewing | offered | rejected
    applied_date = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # 关联岗位对象
    job = db.relationship("Job", backref=db.backref("applications", lazy=True, cascade="all, delete-orphan"))
    # 关联聊天信息，按照自增ID排序
    messages = db.relationship("Chat", backref="application", order_by="Chat.id", lazy=True,
                               cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "job": self.job.to_dict() if self.job else None,
            "status": self.status,
            "appliedDate": self.applied_date,
            "notes": self.notes,
            "messages": [msg.to_dict() for msg in self.messages]
        }


class Chat(db.Model):
    """即时对话消息记录表"""
    __tablename__ = "chats"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    application_id = db.Column(db.String(50), db.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    sender = db.Column(db.String(20), nullable=False)  # user | recruiter
    text = db.Column(db.Text, nullable=False)
    time = db.Column(db.String(20), nullable=False)  # "10:35"
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "sender": self.sender,
            "text": self.text,
            "time": self.time
        }


# ==========================================
# 路由视图 API 控制器
# ==========================================

@app.route("/api/health", methods=["GET"])
def health():
    """生命探测与健康性指标查验"""
    return jsonify({
        "status": "Flask Running Successfully!",
        "database": "MySQL" if USE_MYSQL else "SQLite",
        "timestamp": datetime.now().isoformat()
    })


@app.route("/api/jobs", methods=["GET", "POST"])
def manage_jobs():
    """
    1. 获取岗位清单: GET /api/jobs
    2. 发布新增岗位: POST /api/jobs
    """
    if request.method == "GET":
        jobs_list = Job.query.order_by(Job.created_at.desc()).all()
        return jsonify([j.to_dict() for j in jobs_list])

    elif request.method == "POST":
        data = request.json
        if not data or not data.get("title") or not data.get("company"):
            return jsonify({"error": "缺少必填的职位名称或公司名称详情"}), 400

        # 转换前端数组为扁平文本持久化
        tags_str = ",".join(data.get("tags", []))
        perks_str = ",".join(data.get("perks", []))

        new_job = Job(
            id=data.get("id") or f"job-{int(datetime.now().timestamp() * 1000)}",
            title=data.get("title"),
            salary=data.get("salary") or "薪资面议",
            company=data.get("company"),
            size=data.get("size") or "100-500人",
            industry=data.get("industry") or "互联网",
            tags=tags_str,
            recruiter_name=data.get("recruiterName") or "AI招聘助手",
            recruiter_title=data.get("recruiterTitle") or "智能HR专员",
            recruiter_avatar=data.get(
                "recruiterAvatar") or "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120",
            recruiter_bio=data.get("recruiterBio") or "随时在线，为您秒速解答初筛意向。",
            job_description=data.get("jobDescription") or "1. 负责关联业务线的日常迭代开发维护;\n2. 独立负责中等规模子系统的业务规划落地。",
            perks=perks_str,
            is_hot=data.get("isHot", False)
        )

        db.session.add(new_job)
        db.session.commit()
        return jsonify(new_job.to_dict()), 201


@app.route("/api/applications", methods=["GET", "POST"])
def manage_applications():
    """
    1. 获取所有投递记录及其对应的岗位和历史对话: GET /api/applications
    2. 新增投递记录: POST /api/applications
    """
    if request.method == "GET":
        apps_list = Application.query.order_by(Application.created_at.desc()).all()
        return jsonify([a.to_dict() for a in apps_list])

    elif request.method == "POST":
        data = request.json
        if not data or not data.get("id") or not data.get("job", {}).get("id"):
            return jsonify({"error": "缺少合法的申请ID或关联的岗位数据"}), 400

        job_data = data.get("job")
        # 确保岗位已经存在于数据库，如无则自动关联创建入库
        existing_job = Job.query.get(job_data["id"])
        if not existing_job:
            tags_str = ",".join(job_data.get("tags", []))
            perks_str = ",".join(job_data.get("perks", []))
            auto_job = Job(
                id=job_data["id"],
                title=job_data.get("title"),
                salary=job_data.get("salary"),
                company=job_data.get("company"),
                size=job_data.get("size"),
                industry=job_data.get("industry"),
                tags=tags_str,
                recruiter_name=job_data.get("recruiterName") or "HR",
                recruiter_title=job_data.get("recruiterTitle") or "招聘官",
                recruiter_avatar=job_data.get("recruiterAvatar"),
                recruiter_bio=job_data.get("recruiterBio"),
                job_description=job_data.get("jobDescription"),
                perks=perks_str,
                is_hot=job_data.get("isHot", False)
            )
            db.session.add(auto_job)
            db.session.commit()

        # 查看是否投递过
        existing_app = Application.query.get(data["id"])
        if existing_app:
            return jsonify({"error": "该职位早已发起过投递登记，请直接对话交流"}), 400

        new_app = Application(
            id=data["id"],
            job_id=job_data["id"],
            status=data.get("status") or "applied",
            applied_date=data.get("appliedDate") or datetime.now().strftime("%Y-%m-%d"),
            notes=data.get("notes") or ""
        )
        db.session.add(new_app)
        db.session.commit()

        # 添加首句招聘官欢迎常态语
        initial_msg_txt = f"你好，我是{job_data.get('recruiterName', 'HR')}。我们已收到你的简历，评估后会第一时间答复你！"
        first_chat = Chat(
            application_id=new_app.id,
            sender="recruiter",
            text=initial_msg_txt,
            time=datetime.now().strftime("%H:%M")
        )
        db.session.add(first_chat)
        db.session.commit()

        return jsonify(new_app.to_dict()), 201


@app.route("/api/chat", methods=["POST"])
def save_chat_message():
    """
    保存最新一条聊天日志: POST /api/chat
    """
    data = request.json
    if not data or not data.get("applicationId") or not data.get("text") or not data.get("sender"):
        return jsonify({"error": "参数校验失败，请提供发送者身份、内容及投递会话ID"}), 400

    app_id = data.get("applicationId")
    app_record = Application.query.get(app_id)
    if not app_record:
        return jsonify({"error": "找不到此投递会话，消息保存未成功"}), 404

    # 新增消息入库
    new_chat = Chat(
        application_id=app_id,
        sender=data.get("sender"),
        text=data.get("text"),
        time=data.get("time") or datetime.now().strftime("%H:%M")
    )
    db.session.add(new_chat)

    # 动态把关联申请状态升级为 "chatting"
    app_record.status = "chatting"
    db.session.commit()

    return jsonify({
        "success": True,
        "message": new_chat.to_dict(),
        "applicationStatus": app_record.status
    }), 201


# ==========================================
# 独立运行初始化
# ==========================================

def init_mock_data():
    """注入几个初始岗位"""
    if Job.query.count() == 0:
        mock_jobs = [
            Job(
                id="job-1",
                title="高级UI设计师",
                salary="25k-45k",
                company="某知名科技大厂",
                size="1000-5000人",
                industry="互联网",
                tags="北京 · 中关村,3-5年,本科",
                recruiter_name="王经理",
                recruiter_title="招聘负责人",
                recruiter_avatar="https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?auto=format&fit=crop&q=80&w=120",
                recruiter_bio="从事互联网中高端人才猎寻10年，专注创意与体验设计方向。",
                job_description="1. 负责核心产品的整体视觉创意与UI界面设计；\n2. 参与前瞻性产品的创意规划,主导制定视觉设计规范体系；\n3. 与产品经理及前端开发密切配合，推动设计方案高质量落地。",
                perks="双休/弹性办公,六险一金,免费下午茶",
                is_hot=True
            ),
            Job(
                id="job-2",
                title="后端开发工程师",
                salary="30k-55k",
                company="阿里巴巴集团",
                size="10000人以上",
                industry="互联网",
                tags="杭州 · 余杭区,5-10年,硕士",
                recruiter_name="李总",
                recruiter_title="技术总监",
                recruiter_avatar="https://images.unsplash.com/photo-1560250097-0b93528c311a?auto=format&fit=crop&q=80&w=120",
                recruiter_bio="阿里资深技术总监，前搜索核心架构师，技术卓越，关注开源。",
                job_description="1. 负责核心系统后端服务的设计与高可用架构搭建；\n2. 解决大流量、高并发下的分布式一致性、高可用及高扩展性瓶颈问题；\n3. 导师制带徒，保障团队技术沉淀与代码质量。",
                perks="全额公积金,年终限制股奖,免费每年体检",
                is_hot=True
            ),
            Job(
                id="job-3",
                title="产品经理（AI方向）",
                salary="20k-40k",
                company="字节跳动",
                size="10000人以上",
                industry="人工智能",
                tags="北京 · 海淀区,1-3年,本科",
                recruiter_name="Sarah",
                recruiter_title="招聘专家",
                recruiter_avatar="https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&q=80&w=120",
                recruiter_bio="字节效能与AI算法方向资深HR，支持多个创新项目冷启动招聘。",
                job_description="1. 负责大语言模型应用（模版/智能Agents）在C端产品功能的规划与定义；\n2. 洞察用户痛点，设计闭环人机协同交互链路，提升会话转化和参与度；\n3. 结合AI技术发展推动业务场景创新。",
                perks="双休/弹性办公,六险一金/美味餐补,顶配Mac必备",
                is_hot=True
            )
        ]
        for mj in mock_jobs:
            db.session.add(mj)
        db.session.commit()
        print("[ Flask Backend ] 数据库初始示例岗位批量成功载入！")


if __name__ == "__main__":
    with app.app_context():
        # SQLite 模式下自动触发空库建表，并写入初始岗位数据
        db.create_all()
        init_mock_data()
    print("[ Flask Backend ] 求职助手 Flask API服务已准备绪。")
    app.run(host="0.0.0.0", port=5000, debug=True)
