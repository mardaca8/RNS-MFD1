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

// RNS-MFD1 patch: low-latency replacement for the QMediaPlayer based output.
// appsrc (whole frames) -> h264parse -> avdec_h264 -> appsink (sync=false, newest frame only)
// -> QOpenGLWidget, so frames are shown as soon as they are decoded and never queue up.

#pragma once

#include <QObject>
#include <memory>
#include <mutex>
#include <boost/noncopyable.hpp>
#include <f1x/openauto/autoapp/Projection/VideoOutput.hpp>

typedef struct _GstElement GstElement;

namespace f1x
{
namespace openauto
{
namespace autoapp
{
namespace projection
{

class VideoFrameWidget;

class QtVideoOutput: public QObject, public VideoOutput, boost::noncopyable
{
    Q_OBJECT

public:
    QtVideoOutput(configuration::IConfiguration::Pointer configuration);
    ~QtVideoOutput() override;
    bool open() override;
    bool init() override;
    void write(uint64_t timestamp, const aasdk::common::DataConstBuffer& buffer) override;
    void stop() override;

signals:
    void startPlayback();
    void stopPlayback();

protected slots:
    void createVideoOutput();
    void onStartPlayback();
    void onStopPlayback();

private:
    void stopPipeline();

    std::unique_ptr<VideoFrameWidget> videoWidget_;
    GstElement* pipeline_;
    GstElement* appsrc_;
    std::mutex pipelineMutex_;
};

}
}
}
}
