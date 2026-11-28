/*
*  This file is part of openauto project.
*  Copyright (C) 2018 f1x.studio (Michal Szwaj)
*
*  openauto is free software: you can redistribute it and/or modify
*  it under the terms of the GNU General Public License as published by
*  the Free Software Foundation; either version 3 of the License, or
*  (at your option) any later version.

*  openauto is distributed in the hope that it will be useful,
*  but WITHOUT ANY WARRANTY; without even the implied warranty of
*  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
*  GNU General Public License for more details.
*
*  You should have received a copy of the GNU General Public License
*  along with openauto. If not, see <http://www.gnu.org/licenses/>.
*/

// RNS-MFD1 patch, see QtVideoOutput.hpp.
// GStreamer headers first: Qt's "signals" keyword macro must not reach glib headers.
#include <gst/gst.h>
#include <gst/app/gstappsrc.h>
#include <gst/app/gstappsink.h>
#include <gst/video/video.h>

#include <cstdlib>
#include <mutex>
#include <string>
#include <QApplication>
#include <QGuiApplication>
#include <QImage>
#include <QOpenGLWidget>
#include <QPainter>
#include <QScreen>
#include <f1x/openauto/autoapp/Projection/QtVideoOutput.hpp>
#include <f1x/openauto/Common/Log.hpp>

namespace f1x
{
namespace openauto
{
namespace autoapp
{
namespace projection
{

// Keeps only the newest decoded frame; scaling to the screen happens on the GPU.
class VideoFrameWidget: public QOpenGLWidget
{
public:
    // Called from the GStreamer streaming thread.
    void setFrame(QImage frame)
    {
        std::lock_guard<std::mutex> lock(frameMutex_);
        frame_ = std::move(frame);
        if (!updatePending_)
        {
            updatePending_ = true;
            QMetaObject::invokeMethod(this, [this]() { update(); }, Qt::QueuedConnection);
        }
    }

    void clearFrame()
    {
        std::lock_guard<std::mutex> lock(frameMutex_);
        frame_ = QImage();
    }

protected:
    void paintGL() override
    {
        QImage frame;
        {
            std::lock_guard<std::mutex> lock(frameMutex_);
            frame = frame_;
            updatePending_ = false;
        }

        QPainter painter(this);
        if (frame.isNull())
        {
            painter.fillRect(rect(), Qt::black);
        }
        else
        {
            painter.drawImage(rect(), frame);
        }
    }

private:
    std::mutex frameMutex_;
    QImage frame_;
    bool updatePending_ = false;
};

static GstFlowReturn onNewSample(GstAppSink* sink, gpointer data)
{
    auto widget = static_cast<VideoFrameWidget*>(data);
    GstSample* sample = gst_app_sink_pull_sample(sink);
    if (sample == nullptr)
    {
        return GST_FLOW_OK;
    }

    GstVideoInfo info;
    GstVideoFrame frame;
    if (gst_video_info_from_caps(&info, gst_sample_get_caps(sample)) &&
        gst_video_frame_map(&frame, &info, gst_sample_get_buffer(sample), GST_MAP_READ))
    {
        QImage image(static_cast<const uchar*>(GST_VIDEO_FRAME_PLANE_DATA(&frame, 0)),
                     GST_VIDEO_FRAME_WIDTH(&frame), GST_VIDEO_FRAME_HEIGHT(&frame),
                     GST_VIDEO_FRAME_PLANE_STRIDE(&frame, 0), QImage::Format_RGB32);
        widget->setFrame(image.copy());
        gst_video_frame_unmap(&frame);
    }
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}

static GstBusSyncReply onBusMessage(GstBus*, GstMessage* message, gpointer)
{
    if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR || GST_MESSAGE_TYPE(message) == GST_MESSAGE_WARNING)
    {
        GError* error = nullptr;
        gchar* debug = nullptr;
        if (GST_MESSAGE_TYPE(message) == GST_MESSAGE_ERROR)
        {
            gst_message_parse_error(message, &error, &debug);
            OPENAUTO_LOG(error) << "[QtVideoOutput] GStreamer error: " << error->message << " (" << (debug ? debug : "") << ")";
        }
        else
        {
            gst_message_parse_warning(message, &error, &debug);
            OPENAUTO_LOG(warning) << "[QtVideoOutput] GStreamer warning: " << error->message;
        }
        g_clear_error(&error);
        g_free(debug);
    }
    return GST_BUS_DROP;
}

// Decode chain between appsrc and appsink. Software decoding on purpose: the Pi's v4l2h264dec
// only releases a frame after several more arrive, and Android Auto sends few frames while the
// screen is still, so the picture lagged ~30 s. avdec_h264 with one thread outputs every frame
// immediately. Override for tests without rebuilding, e.g.
// OPENAUTO_VIDEO_PIPELINE="h264parse ! v4l2h264dec ! videoconvert"
static std::string decodeChain()
{
    const char* custom = std::getenv("OPENAUTO_VIDEO_PIPELINE");
    return custom != nullptr && *custom != '\0' ? custom : "h264parse ! avdec_h264 max-threads=1 ! videoconvert";
}

// The black splash window from autoapp.cpp (RNS patch) would cover the video window, so it is
// hidden while video plays and shown again between sessions.
static void setSplashVisible(bool visible)
{
    for (QWidget* widget : QApplication::topLevelWidgets())
    {
        if (widget->objectName() == "rnsSplash")
        {
            OPENAUTO_LOG(info) << "[QtVideoOutput] Splash " << (visible ? "shown" : "hidden");
            if (visible)
            {
                widget->showFullScreen();
            }
            else
            {
                widget->hide();
            }
        }
    }
}

QtVideoOutput::QtVideoOutput(configuration::IConfiguration::Pointer configuration)
    : VideoOutput(std::move(configuration))
    , pipeline_(nullptr)
    , appsrc_(nullptr)
{
    if (!gst_is_initialized())
    {
        gst_init(nullptr, nullptr);
    }

    this->moveToThread(QApplication::instance()->thread());
    connect(this, &QtVideoOutput::startPlayback, this, &QtVideoOutput::onStartPlayback, Qt::BlockingQueuedConnection);
    connect(this, &QtVideoOutput::stopPlayback, this, &QtVideoOutput::onStopPlayback, Qt::BlockingQueuedConnection);
    QMetaObject::invokeMethod(this, "createVideoOutput", Qt::BlockingQueuedConnection);
}

QtVideoOutput::~QtVideoOutput()
{
    OPENAUTO_LOG(info) << "[QtVideoOutput] Destructor called, ensuring cleanup";
    stopPipeline();
}

void QtVideoOutput::createVideoOutput()
{
    OPENAUTO_LOG(info) << "[QtVideoOutput] createVideoOutput() (low-latency GStreamer output)";
    videoWidget_ = std::make_unique<VideoFrameWidget>();
}

bool QtVideoOutput::open()
{
    return true;
}

bool QtVideoOutput::init()
{
    emit startPlayback();
    std::lock_guard<std::mutex> lock(pipelineMutex_);
    return pipeline_ != nullptr;
}

void QtVideoOutput::stop()
{
    emit stopPlayback();
}

void QtVideoOutput::write(uint64_t, const aasdk::common::DataConstBuffer& buffer)
{
    std::lock_guard<std::mutex> lock(pipelineMutex_);
    if (appsrc_ == nullptr)
    {
        return;
    }

    GstBuffer* gstBuffer = gst_buffer_new_allocate(nullptr, buffer.size, nullptr);
    gst_buffer_fill(gstBuffer, 0, buffer.cdata, buffer.size);
    gst_app_src_push_buffer(GST_APP_SRC(appsrc_), gstBuffer);  // takes ownership
}

void QtVideoOutput::onStartPlayback()
{
    OPENAUTO_LOG(info) << "[QtVideoOutput] onStartPlayback()";
    stopPipeline();

    const std::string description =
        "appsrc name=src is-live=true do-timestamp=true format=time stream-type=stream "
        // every Android Auto video message is one whole frame, so h264parse need not wait for the next
        "caps=video/x-h264,stream-format=byte-stream,alignment=au ! " + decodeChain() +
        " ! video/x-raw,format=BGRx ! appsink name=sink sync=false max-buffers=1 drop=true";
    OPENAUTO_LOG(info) << "[QtVideoOutput] Pipeline: " << description;

    GError* error = nullptr;
    GstElement* pipeline = gst_parse_launch(description.c_str(), &error);
    if (pipeline == nullptr || error != nullptr)
    {
        OPENAUTO_LOG(error) << "[QtVideoOutput] Pipeline creation failed: " << (error ? error->message : "unknown");
        g_clear_error(&error);
        if (pipeline != nullptr)
        {
            gst_object_unref(pipeline);
        }
        return;
    }

    GstBus* bus = gst_element_get_bus(pipeline);
    gst_bus_set_sync_handler(bus, onBusMessage, nullptr, nullptr);
    gst_object_unref(bus);

    GstElement* sink = gst_bin_get_by_name(GST_BIN(pipeline), "sink");
    GstAppSinkCallbacks callbacks = {};
    callbacks.new_sample = onNewSample;
    gst_app_sink_set_callbacks(GST_APP_SINK(sink), &callbacks, videoWidget_.get(), nullptr);
    gst_object_unref(sink);

    videoWidget_->clearFrame();
    setSplashVisible(false);
    videoWidget_->setWindowFlags(Qt::Window | Qt::FramelessWindowHint);
    QScreen* screen = QGuiApplication::primaryScreen();
    if (screen != nullptr)
    {
        videoWidget_->setGeometry(screen->geometry());
        OPENAUTO_LOG(info) << "[QtVideoOutput] Set video widget geometry to: "
                           << screen->geometry().width() << "x" << screen->geometry().height();
    }
    else
    {
        videoWidget_->showFullScreen();
    }
    videoWidget_->raise();
    videoWidget_->show();
    videoWidget_->setFocus();
    videoWidget_->activateWindow();

    if (gst_element_set_state(pipeline, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE)
    {
        OPENAUTO_LOG(error) << "[QtVideoOutput] Pipeline failed to start";
        gst_element_set_state(pipeline, GST_STATE_NULL);
        gst_object_unref(pipeline);
        return;
    }

    std::lock_guard<std::mutex> lock(pipelineMutex_);
    pipeline_ = pipeline;
    appsrc_ = gst_bin_get_by_name(GST_BIN(pipeline), "src");
    OPENAUTO_LOG(info) << "[QtVideoOutput] Pipeline playing";
}

void QtVideoOutput::stopPipeline()
{
    GstElement* pipeline;
    GstElement* appsrc;
    {
        std::lock_guard<std::mutex> lock(pipelineMutex_);
        pipeline = pipeline_;
        appsrc = appsrc_;
        pipeline_ = nullptr;
        appsrc_ = nullptr;
    }

    if (appsrc != nullptr)
    {
        gst_object_unref(appsrc);
    }
    if (pipeline != nullptr)
    {
        gst_element_set_state(pipeline, GST_STATE_NULL);  // joins the streaming threads
        gst_object_unref(pipeline);
    }
}

void QtVideoOutput::onStopPlayback()
{
    OPENAUTO_LOG(info) << "[QtVideoOutput] onStopPlayback()";
    stopPipeline();
    if (videoWidget_)
    {
        videoWidget_->hide();
        videoWidget_->clearFocus();
    }
    setSplashVisible(true);
    OPENAUTO_LOG(info) << "[QtVideoOutput] onStopPlayback() complete";
}

}
}
}
}
